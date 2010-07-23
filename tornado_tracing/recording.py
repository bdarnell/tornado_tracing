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

