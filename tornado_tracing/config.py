import functools
import memcache
import tornado.web
import tornado.wsgi
import warnings

with warnings.catch_warnings():
    warnings.simplefilter('ignore', DeprecationWarning)
    from google.appengine.api import memcache as appengine_memcache
    from google.appengine.api import lib_config
    from google.appengine.ext import webapp

def setup_memcache(*args, **kwargs):
    '''Configures the app engine memcache interface with a set of regular
    memcache servers.  All arguments are passed to the memcache.Client
    constructor.

    Example:
      setup_memcache(["localhost:11211"])
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
        tornado_tracing.config.get_urlspec(r'/_stats/.*'),
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

def set_options(**kwargs):
    '''Sets configuration options for appstats.  See
    /usr/local/google_appengine/ext/appstats/recording.py for possible keys.

    Example:
    tornado_tracing.config.set_options(RECORD_FRACTION=0.1,
                                       KEY_PREFIX='__appstats_myapp__')
    '''
    lib_config.register('appstats', kwargs)
