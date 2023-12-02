# coding: utf-8
import wave
import sys
import pyaudio

p = pyaudio.PyAudio()
CHUNK = 1024
wfs = { }
def load_wav(path):
    wf = wave.open(path, 'rb')
    wfs[path] = wf
    return wf
    
def play(path):
    if wf := wfs.get(path):
        stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True)
        while len(data := wf.readframes(CHUNK)):
            stream.write(data)
        wf.setpos(0)
        return stream
    else:
        print('sound not loaded:', path)
             
def close():
    # Release PortAudio system resources
    for path, wf in wfs.items():
        wf.close()
    p.terminate()
