#!/usr/bin/env python
import asyncio
from collections import deque
from asyncio.subprocess import PIPE
import logging
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(format=logging.DEBUG)

IMAGES=['yarara/python-3.4.1:v1',
        'yarara/python-3.4.0:v1',
        'yarara/python-3.3.5:v1',
        'yarara/python-3.3.4:v1',
        'yarara/python-3.3.3:v1',
        'yarara/python-3.3.2:v1',
        'yarara/python-3.3.1:v1',
        'yarara/python-3.3.0:v1',
        'yarara/python-3.2:v1',
        'yarara/python-3.2.5:v1',
        'yarara/python-3.2.4:v1',
        'yarara/python-3.2.3:v1',
        'yarara/python-3.2.2:v1',
        'yarara/python-3.2.1:v1',
        'yarara/python-3.1:v1',
        'yarara/python-3.1.5:v1',
        'yarara/python-3.1.4:v1',
        'yarara/python-3.1.3:v1',
        'yarara/python-3.1.2:v1',
        'yarara/python-3.1.1:v1',
        'yarara/python-3.0:v1',
        'yarara/python-3.0.1:v1',
        'yarara/python-2.7:v1',
        'yarara/python-2.7.8:v1',
        'yarara/python-2.7.7:v1',
        'yarara/python-2.7.6:v1',
        'yarara/python-2.7.5:v1',
        'yarara/python-2.7.4:v1',
        'yarara/python-2.7.3:v1',
        'yarara/python-2.7.2:v1',
        'yarara/python-2.7.1:v1',
        'yarara/python-2.6:v1',
        'yarara/python-2.6.9:v1',
        'yarara/python-2.6.8:v1',
        'yarara/python-2.6.7:v1',
        'yarara/python-2.6.6:v1',
        'yarara/python-2.6.5:v1',
        'yarara/python-2.6.4:v1',
        'yarara/python-2.6.3:v1',
        'yarara/python-2.6.2:v1',
        'yarara/python-2.6.1:v1',
        'yarara/python-2.5:v1',
        'yarara/python-2.5.6:v1',
        'yarara/python-2.5.5:v1',
        'yarara/python-2.5.4:v1',
        'yarara/python-2.5.3:v1',
        'yarara/python-2.5.2:v1',
        'yarara/python-2.5.1:v1',
        'yarara/python-2.4:v1',
        'yarara/python-2.4.6:v1',
        'yarara/python-2.4.5:v1',
        'yarara/python-2.4.4:v1',
        'yarara/python-2.4.3:v1',
        'yarara/python-2.4.2:v1',
        'yarara/python-2.4.1:v1',
        'yarara/python-2.3:v1',
        'yarara/python-2.3.7:v1',
        'yarara/python-2.3.6:v1',
        'yarara/python-2.3.5:v1',
        'yarara/python-2.3.4:v1',
        'yarara/python-2.3.3:v1',
        'yarara/python-2.3.1:v1',
        'yarara/python-2.2:v1',
        'yarara/python-2.2.3:v1',
        'yarara/python-2.2.2:v1',
        'yarara/python-2.2.1:v1',
        'yarara/python-2.1:v1',
        'yarara/python-2.1.3:v1',
        'yarara/python-2.1.2:v1',
        'yarara/python-2.1.1:v1',
        'yarara/python-2.0.1:v1',
        'yarara/python-2.3.2:v1']


CMD = "docker run -i {} /yarara/bin/python -i -"
process_queue = asyncio.Queue()


@asyncio.coroutine
def send_input(image, stream, stream_name, input_, has_prompt=None):
    try:
        for line in input_.splitlines():
            yield from has_prompt.wait()
            stream.write(line)
            stream.write(b'\n')
            d = stream.drain()
            if d:
                yield from d
            yield from process_queue.put({'image': image, stream_name: line})
            has_prompt.clear()
        stream.close()
    except BrokenPipeError:
        pass
    except ConnectionResetError:
        pass

def is_prompt(buf):
    return buf in (b'>>> ', b'... ')

@asyncio.coroutine
def read_stream(image, stream, stream_name, has_prompt=None):
    last_chars = deque(maxlen=4)
    line = []

    while True:
        char = yield from stream.read(1)

        if not char:
            break

        if has_prompt:
            last_chars.append(char)
            if char == b' ':
                chunk = b''.join(last_chars)
                if is_prompt(chunk):
                    has_prompt.set()

        line.append(char)
        if char == b'\n' or (has_prompt and is_prompt(b''.join(last_chars))):
            yield from process_queue.put({'image': image, stream_name: b''.join(line)})
            line = []


@asyncio.coroutine
def execute(input_, image):
    process = yield from asyncio.create_subprocess_shell(
        CMD.format(image), stdin=PIPE, stdout=PIPE, stderr=PIPE)

    has_prompt = asyncio.Event()
    yield from asyncio.wait([
        send_input(image, process.stdin, 'stdin', input_, has_prompt),
        read_stream(image, process.stdout, 'stdout'),
        read_stream(image, process.stderr, 'stderr', has_prompt)])

    retval = yield from process.wait()
    yield from process_queue.put({'image': image, 'retval': retval})


@asyncio.coroutine
def print_output():
    while True:
        line = yield from process_queue.get()
        if line is None:
            break
        print(line)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    with open(sys.argv[1], 'r') as inputfile:
        input_ = inputfile.read().encode('utf-8')

    tasks = []
    for image in IMAGES:
        tasks.append(execute(input_, image))

    printer = asyncio.Task(print_output())
    loop.run_until_complete(asyncio.wait(tasks))
    process_queue.put_nowait(None)
    loop.run_until_complete(printer)
