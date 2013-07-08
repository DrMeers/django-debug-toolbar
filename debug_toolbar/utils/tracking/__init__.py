import logging
import time
import types
from django.utils import six
from django.utils.importlib import import_module

# http://docs.python.org/3/whatsnew/3.0.html#operators-and-special-methods
# Python 3 unbound methods don't contain a reference to their containing
# class, so we need to pass this explicitly going forward.

def post_dispatch(func, cls=None):
    def wrapped(callback):
        register_hook(func, 'after', callback, cls=cls)
        return callback
    return wrapped


def pre_dispatch(func, cls=None):
    def wrapped(callback):
        register_hook(func, 'before', callback, cls=cls)
        return callback
    return wrapped


def replace_call(func=None, cls=None):
    def inner(callback):
        def wrapped(*args, **kwargs):
            return callback(func, *args, **kwargs)

        actual = getattr(func, '__wrapped__', func)
        wrapped.__wrapped__ = actual
        wrapped.__doc__ = getattr(actual, '__doc__', None)
        wrapped.__name__ = actual.__name__

        _replace_function(func, wrapped, cls=cls)
        return wrapped
    return inner


def fire_hook(hook, sender, **kwargs):
    try:
        for callback in callbacks[hook].get(id(sender), []):
            callback(sender=sender, **kwargs)
    except Exception as e:
        # Log the exception, dont mess w/ the underlying function
        logging.exception(e)

def _replace_function(func, wrapped, cls=None):
    if six.PY3 and cls:
        # settattr(cls, ...) does work here in PY2
        setattr(cls, func.__name__, wrapped)
    elif isinstance(func, types.FunctionType):
        if func.__module__ == '__builtin__':
            # oh shit
            __builtins__[func] = wrapped
        else:
            module = import_module(func.__module__)
            setattr(module, func.__name__, wrapped)
    elif getattr(func, 'im_self', None): # PY2
        setattr(func.im_self, func.__name__, classmethod(wrapped))
    elif hasattr(func, 'im_class'): # PY2
        # for unbound methods
        setattr(func.im_class, func.__name__, wrapped)
    else:
        raise NotImplementedError

callbacks = {
    'before': {},
    'after': {},
}


def register_hook(func, hook, callback, cls=None):
    """
    def myhook(sender, args, kwargs):
        print func, "executed
        print "args:", args
        print "kwargs:", kwargs
    register_hook(
        BaseDatabaseWrapper.cursor, 'before', myhook, cls=BaseDatabaseWrapper)
    """

    assert hook in ('before', 'after')

    def wrapped(*args, **kwargs):
        start = time.time()
        fire_hook('before', sender=wrapped.__wrapped__, args=args, kwargs=kwargs,
                  start=start)
        result = wrapped.__wrapped__(*args, **kwargs)
        stop = time.time()
        fire_hook('after', sender=wrapped.__wrapped__, args=args, kwargs=kwargs,
                  result=result, start=start, stop=stop)
    actual = getattr(func, '__wrapped__', func)
    wrapped.__wrapped__ = actual
    wrapped.__doc__ = getattr(actual, '__doc__', None)
    wrapped.__name__ = actual.__name__

    id_ = id(actual)
    if id_ not in callbacks[hook]:
        callbacks[hook][id_] = []
    callbacks[hook][id_].append(callback)

    _replace_function(func, wrapped, cls=cls)
