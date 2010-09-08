Tornado Tracing
===============
This library instruments HTTP calls in a [Tornado](http://tornadoweb.org)
application and provides visualizations to find where your app is spending
its time and identify opportunities for parallelism.  It uses the
[Appstats](http://code.google.com/appengine/docs/python/tools/appstats.html)
module from the Google App Engine SDK.

Tornado Tracing is licensed under the Apache License, Version 2.0
(http://www.apache.org/licenses/LICENSE-2.0.html).

Installation
============
You will need:
* [Tornado](http://tornadoweb.org), version 1.1 or higher
* The [Google App Engine SDK](http://code.google.com/appengine/downloads.html)
* A memcached server and the [python memcache client library](http://www.tummy.com/Community/software/python-memcached/)

Usage
=====
In most cases, you can simply use/subclass `RecordingRequestHandler`
and `AsyncHTTPClient` from `tornado_tracing.recording` instead of the
corresponding Tornado classes.  These classes do nothing special unless
the `--enable_appstats` flag is passed.

At startup, you must call `tornado_tracing.config.setup_memcache()` to tell
the system where your memcache server is running.  You can also use
`tornado_tracing.config.set_options()` to set certain other options,
such as `KEY_PREFIX` if multiple applications are sharing a memcache server
and you want to keep the data separate.

Finally, add `tornado_tracing.config.get_urlspec()` to your `Application`'s
list of handlers.  This is where the trace output will be visible.
Note that the UI does not have to be served from the same process where
the data is generated, as long as they're all using the same memcache.

Screenshot
==========
![screenshot](http://github.com/bdarnell/tornado_tracing/raw/master/demo/screenshot.png)