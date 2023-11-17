import queue
import sys
import os
import threading

import sounddevice as sd
import soundfile as sf

class args:
    blocksize = 2048
    buffersize = 20
    assets_dir = "../assets"

#q = queue.Queue(maxsize=args.buffersize)
#event = threading.Event()

def cb_wrap(q):#, outdata, frames, time, status):
    def callback(outdata, frames, time, status):
        assert frames == args.blocksize
        if status.output_underflow:
            print('Output underflow: increase blocksize?', file=sys.stderr)
            raise sd.CallbackAbort
        assert not status
        try:
            data = q.get_nowait()
            if data.ndim == 1:
                data = data.reshape(-1,1)
        except queue.Empty as e:
            print('Buffer is empty: increase buffersize?', file=sys.stderr)
            raise sd.CallbackAbort from e

        if len(data) < len(outdata):
            outdata[:len(data)] = data
            outdata[len(data):].fill(0)
            raise sd.CallbackStop
        else:
            outdata[:] = data
    return callback


def clear(q):
    for _ in range(q.qsize()):
        print(q.get())

def play_threaded(filename, buffered=False):
    play = play_buffered if buffered else play_short
    threading.Thread(target=play, args=(filename,)).start()

sound_files = list(os.scandir(os.path.join(args.assets_dir,'sounds','patches','numbers')))
print(sound_files)
sounds = [sf.read(f, always_2d=True) for f in sound_files]

def play_short(sound_id):#filename):
    #filename = os.path.join(args.assets_dir, filename)
    #data, fs = sf.read(filename, always_2d=True)
    data, fs = sounds[sound_id]

    event = threading.Event()
    current_frame = 0
    def callback(outdata, frames, time, status):
        nonlocal current_frame
        if status:
            print(status)
        chunksize = min(len(data) - current_frame, frames)
        outdata[:chunksize] = data[current_frame:current_frame + chunksize]
        if chunksize < frames:
            outdata[chunksize:] = 0
            raise sd.CallbackStop()
        current_frame += chunksize

    stream = sd.OutputStream(
        samplerate=fs, channels=data.shape[1],
        callback=callback, finished_callback=event.set)
    with stream:
        event.wait()  # Wait until playback is finished

def play_buffered(filename):
    filename = os.path.join(args.assets_dir, filename)
    q = queue.Queue(maxsize=args.buffersize)
    event = threading.Event()
    try:
        with sf.SoundFile(filename) as f:
            for _ in range(args.buffersize):
                data = f.read(args.blocksize)
                if not len(data):
                    break
                q.put_nowait(data)  # Pre-fill queue
            stream = sd.OutputStream(
                samplerate=f.samplerate, blocksize=args.blocksize,
                channels=f.channels,
                callback=cb_wrap(q), finished_callback=event.set)
            print('sr:',f.samplerate, 'chans:', f.channels)
            with stream:
                timeout = args.blocksize * args.buffersize / f.samplerate
                while len(data):
                    data = f.read(args.blocksize)
                    q.put(data, timeout=timeout)
                event.wait()  # Wait until playback is finished
                clear(q) 
                event.clear()
    except Exception as e:
        print('whoops...', type(e))
        sys.exit()
