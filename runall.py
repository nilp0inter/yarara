#!/usr/bin/env python
import asyncio
from collections import deque
from asyncio.subprocess import PIPE
import logging
import sys
import streamdiffer as sd
from collections import namedtuple

RunningProcess = namedtuple('RunningProcess', ['task', 'stdin'])

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
#        'yarara/python-2.7:v1',
        'yarara/python-2.7.8:v1',
        'yarara/python-2.7.7:v1',
        'yarara/python-2.7.6:v1',
        'yarara/python-2.7.5:v1',
        'yarara/python-2.7.4:v1',
        'yarara/python-2.7.3:v1',
        'yarara/python-2.7.2:v1',
#        'yarara/python-2.7.1:v1',
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


@asyncio.coroutine
def dispatch_stdin(input_queue, processes_stdin):
    while True:
        line = yield from input_queue.get()
        print(repr(line))
        for stdin in processes_stdin:
            stdin.put_nowait(line)
        if line is None:
            break


@asyncio.coroutine
def send_input(image, stream, stream_name, input_, has_prompt=None):
    try:
        while True:
            line = yield from input_.get()
            if line is None:
                break
            line = line.encode('utf-8')
            yield from has_prompt.wait()
            stream.write(line)
            stream.write(b'\n')
            d = stream.drain()
            if d:
                yield from d
            has_prompt.clear()
        stream.close()
    except BrokenPipeError:
        pass
    except ConnectionResetError:
        pass


def is_prompt(buf):
    return buf in (b'>>> ', b'... ')


@asyncio.coroutine
def read_stream(image, stream, stream_name, output_queue, has_prompt=None):
    last_chars = deque(maxlen=4)
    line = []
    lines = 0

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

        if char == b'\n' or (has_prompt and is_prompt(b''.join(last_chars))):
            yield from output_queue.put({'image': image, stream_name: (b''.join(line)).decode('utf-8')})
            line = []
            lines += 1
            if lines > 1:
                stream_name = 'stdout'
        else:
            line.append(char)


@asyncio.coroutine
def execute(image, input_, output):

    process = yield from asyncio.create_subprocess_shell(
        CMD.format(image), stdin=PIPE, stdout=PIPE, stderr=PIPE)

    has_prompt = asyncio.Event()
    yield from asyncio.wait([
        send_input(image, process.stdin, 'stdin', input_, has_prompt),
        read_stream(image, process.stdout, 'stdout', output),
        read_stream(image, process.stderr, 'stderr', output, has_prompt)])

    retval = yield from process.wait()
    yield from output.put({'image': image, 'retval': retval})



def fromcmd():
    loop = asyncio.get_event_loop()

    with open(sys.argv[1], 'r') as inputfile:
        input_ = inputfile.read().encode('utf-8')

    tasks = []
    for image in IMAGES:
        tasks.append(execute(input_, image))
    ready = True

    printer = asyncio.Task(print_output())
    loop.run_until_complete(asyncio.wait(tasks))
    process_queue.put_nowait(None)
    loop.run_until_complete(printer)


def d3_graph(streams, clusters):
    links = []
    for idx, cluster in enumerate(clusters):
        for stream in cluster.streams:
            links.append({'source': streams[stream],
                          'target': "Cluster #{}".format(idx),
                          'type': 'licensing'})
    return links


@asyncio.coroutine
def dispatch_output(output_queue, websocket):
    import json
    try:
        streams = {k: sd.Stream() for k in IMAGES}
        stream_names = {v: k for k, v in streams.items()}

        diff = sd.Differ(list(streams.values()))

        num_clusters = 0
        while True:
            data = yield from output_queue.get()
            if 'stdout' in data:
                diff.update_stream(streams[data['image']], data['stdout'])
                current_num_clusters = len(diff.clusters)
                if num_clusters != current_num_clusters:
                    num_clusters = current_num_clusters
                    links = d3_graph(stream_names, diff.clusters)
                    yield from websocket.send(json.dumps({'links': links}))
            yield from websocket.send(json.dumps(data))
    except Exception as err:
        import traceback
        traceback.print_exc()
        print(data)
        print(err)


@asyncio.coroutine
def print_output():
    num_clusters = 0
    while True:
        line = yield from process_queue.get()
        if line is None:
            break

        if 'stdout' in line:
            diff.update_stream(streams[line['image']], line['stdout'])
            current_num_clusters = len(diff.clusters)
            if num_clusters != current_num_clusters:
                print(len(diff.clusters))
                for cluster in diff.clusters:
                    print(repr(list(cluster.streams)[0]))
                num_clusters = current_num_clusters


@asyncio.coroutine
def run_processes(websocket, path):

    # Start all the processes when the first line arrives.
    line = yield from websocket.recv()

    output_queue = asyncio.Queue()
    input_queue = asyncio.Queue()

    processes = []
    for image in IMAGES:
        process_input_queue = asyncio.Queue()

        task = execute(image, process_input_queue, output_queue)
        process = RunningProcess(asyncio.Task(task), process_input_queue)

        processes.append(process)

    asyncio.Task(dispatch_stdin(input_queue, [p.stdin for p in processes]))
    asyncio.Task(dispatch_output(output_queue, websocket))

    # Finally put the first line in the input queue.
    yield from input_queue.put(line)

    while True:
        line = yield from websocket.recv()
        yield from input_queue.put(line)
        if line is None:
            break


if __name__ == '__main__':
    import websockets

    @asyncio.coroutine
    def hello(websocket, path):
        name = yield from websocket.recv()
        print("< {}".format(name))
        greeting = "Hello {}!".format(name)
        print("> {}".format(greeting))
        yield from websocket.send(greeting)

    start_server = websockets.serve(run_processes, '0.0.0.0', 8765)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
