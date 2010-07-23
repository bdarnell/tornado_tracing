'''RPC Tracing support.

Records timing information about rpcs and other operations for performance
profiling.  Currently just a wrapper around the Google App Engine appstats
module.
'''

import contextlib
import functools
import logging
import memcache
import tornado.httpclient
import tornado.web
import tornado.wsgi
import warnings

with warnings.catch_warnings():
  warnings.simplefilter('ignore', DeprecationWarning)
  from google.appengine.api import memcache as appengine_memcache
  from google.appengine.api import lib_config
  from google.appengine.ext import webapp
  from google.appengine.ext.appstats import recording
  from google.appengine.ext.appstats.recording import (
    start_recording, end_recording, pre_call_hook, post_call_hook)
from tornado.httpclient import AsyncHTTPClient
from tornado.options import define, options
from tornado.stack_context import StackContext
from tornado.web import RequestHandler

define('enable_appstats', type=bool, default=False)

class RecordingRequestHandler(RequestHandler):
  def __init__(self, *args, **kwargs):
    super(RecordingRequestHandler, self).__init__(*args, **kwargs)
    self.__recorder = None

  def _execute(self, transforms, *args, **kwargs):
    if options.enable_appstats:
      start_recording(tornado.wsgi.WSGIContainer.environ(self.request))
      recorder = recording.recorder
      @contextlib.contextmanager
      def transfer_recorder():
        recording.recorder = recorder
        yield
      with StackContext(transfer_recorder):
        super(RecordingRequestHandler, self)._execute(transforms,
                                                      *args, **kwargs)
    else:
      super(RecordingRequestHandler, self)._execute(transforms,
                                                    *args, **kwargs)

  def finish(self, chunk=None):
    super(RecordingRequestHandler, self).finish(chunk)
    if options.enable_appstats:
      end_recording(self._status_code)

class RecordingFallbackHandler(tornado.web.FallbackHandler):
  def prepare(self):
    if options.enable_appstats:
      recording.start_recording(
        tornado.wsgi.WSGIContainer.environ(self.request))
      recorder = recording.recorder
      @contextlib.contextmanager
      def transfer_recorder():
        recording.recorder = recorder
        yield
      with StackContext(transfer_recorder):
        super(RecordingFallbackHandler, self).prepare()
      recording.end_recording(self._status_code)
    else:
      super(RecordingFallbackHandler, self).prepare()

def setup_memcache(*args, **kwargs):
  '''Configures the app engine memcache interface with a set of regular
  memcache servers.  All arguments are passed to the memcache.Client
  constructor.
  '''
  client = memcache.Client(*args, **kwargs)
  # The appengine memcache interface has some methods that aren't
  # currently available in the regular memcache module (at least
  # in version 1.4.4).  Fortunately appstats doesn't use them, but
  # the setup_client function expects them to be there.
  client.add_multi = None
  client.replace_multi = None
  client.offset_multi = None
  # Appengine adds a 'namespace' parameter to many methods.  Since
  # appstats.recording uses both namespace and key_prefix, just drop
  # the namespace.  (This list of methods is not exhaustive, it's just
  # the ones appstats uses)
  for method in ('set_multi', 'set', 'add', 'delete', 'get', 'get_multi'):
    def wrapper(old_method, *args, **kwargs):
      # appstats.recording always passes namespace by keyword
      if 'namespace' in kwargs:
        del kwargs['namespace']
      return old_method(*args, **kwargs)
    setattr(client, method,
            functools.partial(wrapper, getattr(client, method)))
  appengine_memcache.setup_client(client)

def get_urlspec(prefix):
  '''Returns a tornado.web.URLSpec for the appstats UI.
  Should be mapped to a url prefix ending with 'stats/'.

  Example:
    app = tornado.web.Application([
      ...
      recording.get_urlspec(r'/_stats/.*'),
      ])
  '''
  # This import can't happen at the top level because things get horribly
  # confused if it happens before django settings are initialized.
  with warnings.catch_warnings():
    warnings.simplefilter('ignore', DeprecationWarning)
    from google.appengine.ext.appstats import ui
  wsgi_app = tornado.wsgi.WSGIContainer(webapp.WSGIApplication(ui.URLMAP))
  return tornado.web.url(prefix,
                         tornado.web.FallbackHandler,
                         dict(fallback=wsgi_app))

def save():
  return recording.recorder

def restore(recorder):
  recording.recorder = recorder

def _recording_request(request):
  if isinstance(request, tornado.httpclient.HTTPRequest):
    return request.url
  else:
    return request

class HTTPClient(tornado.httpclient.HTTPClient):
  def fetch(self, request, *args, **kwargs):
    recording_request = _recording_request(request)
    recording.pre_call_hook('http', 'sync', recording_request, None)
    response = super(HTTPClient, self).fetch(request, *args, **kwargs)
    recording.post_call_hook('http', 'sync', recording_request, None)
    return response

class AsyncHTTPClient(AsyncHTTPClient):
  def fetch(self, request, callback, *args, **kwargs):
    recording_request = _recording_request(request)
    recording.pre_call_hook('http', 'async', recording_request, None)
    def wrapper(request, callback, response, *args):
      recording.post_call_hook('http', 'async', recording_request, None)
      callback(response)
    super(AsyncHTTPClient, self).fetch(
      request,
      functools.partial(wrapper, request, callback),
      *args, **kwargs)

def config(**kwargs):
  '''Sets configuration options for appstats.  See
  /usr/local/google_appengine/ext/appstats/recording.py for possible keys.

  Example:
  recording.config(RECORD_FRACTION=0.1,
                   KEY_PREFIX='__appstats_myapp__')
  '''
  lib_config.register('appstats', kwargs)
