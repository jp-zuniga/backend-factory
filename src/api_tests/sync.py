from collections.abc import Awaitable, Callable

from asgiref.sync import async_to_sync

########################################################################################


def run[**P, T](
    func: Callable[P, Awaitable[T]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    return async_to_sync(func)(*args, **kwargs)
