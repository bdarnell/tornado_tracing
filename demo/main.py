#!/usr/bin/env python
'''Demo of appstats tracing.

Starts a simple server with appstats enabled.  Go to http://localhost:8888/
to generate some sample data, then go to http://localhost:8888/appstats/
to see the results.

Requires tornado, tornado_tracing, and the google appengine sdk to be
on $PYTHONPATH.  It also doesn't like it when the app is started using
a relative path, so run it with something like this:

  export PYTHONPATH=.:../tornado:/usr/local/google_appengine:/usr/local/google_appengine/lib/webob
  $PWD/demo/main.py
'''

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from tornado.web import Application, asynchronous
from tornado_tracing import recording

import time

define('port', type=int, default=8888)
define('memcache', default='localhost:11211')

class DelayHandler(recording.RecordingRequestHandler):
  @asynchronous
  def get(self):
    IOLoop.instance().add_timeout(
      time.time() + int(self.get_argument('ms')) / 1000.0,
      self.handle_timeout)

  def handle_timeout(self):
    self.finish("ok")

# A handler that performs several HTTP requests taking different amount of
# time.  It waits for the first request to finish, then issues three requests
# in parallel.
class RootHandler(recording.RecordingRequestHandler):
  @asynchronous
  def get(self):
    self.client = recording.AsyncHTTPClient()
    self.client.fetch('http://localhost:%d/delay?ms=100' % options.port,
                      self.step2)

  def handle_step2_fetch(self, response):
    assert response.body == 'ok'
    self.fetches_remaining -= 1
    if self.fetches_remaining == 0:
      self.step3()

  def step2(self, response):
    assert response.body == 'ok'
    self.fetches_remaining = 3
    self.client.fetch('http://localhost:%d/delay?ms=50' % options.port,
                      self.handle_step2_fetch)
    self.client.fetch('http://localhost:%d/delay?ms=20' % options.port,
                      self.handle_step2_fetch)
    self.client.fetch('http://localhost:%d/delay?ms=30' % options.port,
                      self.handle_step2_fetch)

  def step3(self):
    self.finish('All done. See results <a href="/appstats/">here</a>.')

def main():
  parse_command_line()
  # doesn't make much sense to run this without appstats enabled
  options.enable_appstats = True
  recording.setup_memcache([options.memcache])

  app = Application([
      ('/', RootHandler),
      ('/delay', DelayHandler),
      recording.get_urlspec('/appstats/.*'),
      ], debug=True)
  server = HTTPServer(app)
  server.listen(options.port)
  IOLoop.instance().start()

if __name__ == '__main__':
  main()
