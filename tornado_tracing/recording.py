'''RPC Tracing support.

Records timing information about rpcs and other operations for performance
profiling.  Currently just a wrapper around the Google App Engine appstats
module.
'''

import contextlib
import functools
import logging
import tornado.httpclient
import tornado.web
import tornado.wsgi
import warnings

with warnings.catch_warnings():
  warnings.simplefilter('ignore', DeprecationWarning)
  from google.appengine.ext.appstats import recording
from tornado.httpclient import AsyncHTTPClient
from tornado.options import define, options
from tornado.stack_context import StackContext
from tornado.web import RequestHandler

define('enable_appstats', type=bool, default=False)

# These methods from the appengine recording module are a part of our
# public API.

# start_recording(wsgi_environ) creates a recording context
start_recording = recording.start_recording
# end_recording(http_status) terminates a recording context
end_recording = recording.end_recording

# pre/post_call_hook(service, method, request, response) mark the
# beginning/end of a time span to record in the trace.
pre_call_hook = recording.pre_call_hook
post_call_hook = recording.post_call_hook

def save():
  '''Returns an object that can be passed to restore() to resume
  a suspended record.
  '''
  return recording.recorder

def restore(recorder):
  '''Reactivates a previously-saved recording context.'''
  recording.recorder = recorder


class RecordingRequestHandler(RequestHandler):
  '''RequestHandler subclass that establishes a recording context for each
  request.
  '''
  def __init__(self, *args, **kwargs):
    super(RecordingRequestHandler, self).__init__(*args, **kwargs)
    self.__recorder = None

  def _execute(self, transforms, *args, **kwargs):
    if options.enable_appstats:
      start_recording(tornado.wsgi.WSGIContainer.environ(self.request))
      recorder = save()
      @contextlib.contextmanager
      def transfer_recorder():
        restore(recorder)
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
  '''FallbackHandler subclass that establishes a recording context for
  each request.
  '''
  def prepare(self):
    if options.enable_appstats:
      recording.start_recording(
        tornado.wsgi.WSGIContainer.environ(self.request))
      recorder = save()
      @contextlib.contextmanager
      def transfer_recorder():
        restore(recorder)
        yield
      with StackContext(transfer_recorder):
        super(RecordingFallbackHandler, self).prepare()
      recording.end_recording(self._status_code)
    else:
      super(RecordingFallbackHandler, self).prepare()

def _request_info(request):
  '''Returns a tuple (method, url) for use in recording traces.

  Accepts either a url or HTTPRequest object, like HTTPClient.fetch.
  '''
  if isinstance(request, tornado.httpclient.HTTPRequest):
    return (request.method, request.url)
  else:
    return ('GET', request)

class HTTPClient(tornado.httpclient.HTTPClient):
  def fetch(self, request, *args, **kwargs):
    method, url = _request_info(request)
    recording.pre_call_hook('HTTP', method, url, None)
    response = super(HTTPClient, self).fetch(request, *args, **kwargs)
    recording.post_call_hook('HTTP', method, url, None)
    return response

class AsyncHTTPClient(AsyncHTTPClient):
  def fetch(self, request, callback, *args, **kwargs):
    method, url = _request_info(request)
    recording.pre_call_hook('HTTP', method, url, None)
    def wrapper(request, callback, response, *args):
      recording.post_call_hook('HTTP', method, url, None)
      callback(response)
    super(AsyncHTTPClient, self).fetch(
      request,
      functools.partial(wrapper, request, callback),
      *args, **kwargs)

