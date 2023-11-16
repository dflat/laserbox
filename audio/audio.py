import sounddevice as sd
import soundfile as sf
import numpy as np

def play_audio(path, event, dev=None):
    data, fs = sf.read(path, always_2d=True)
    
    def rms(arr): return np.sqrt(np.mean(arr**2))
    
    def get_average_energy(data, chunksize=202):
        energies = []
        for i in range(int(len(data)/chunksize)):
            energies.append(rms(data[i*chunksize:(i+1)*chunksize]))
        return np.min(energies), np.max(energies), np.average(energies) 
        
    mn,mx,avg = get_average_energy(data, chunksize=202)
    def rescale(t,a=0,b=1,mn=mn,mx=mx):
        return int(80*(t/mx))*'*'
        
    
    frame = 0
    def callback(outdata, frames, ctime, status):
        nonlocal frame
        if status:
            print(status)
        chunksize = min(len(data) - frame, frames)
        samples = data[frame:frame + chunksize]
        outdata[:chunksize] = samples 
        
        #print(rescale(rms(samples)))
        
        if chunksize < frames:
            outdata[chunksize:] = 0
            raise sd.CallbackStop()
        frame += chunksize
    
    stream = sd.OutputStream(
        samplerate=fs,
        channels=data.shape[1],
        callback=callback,
        finished_callback=event.set)
        
    with stream:
        event.wait()

def compose(*fs):
    def wrapped(x):
        for f in fs[::-1]:
            x = f(x)
        return x
    return wrapped

rms = compose(np.sqrt, np.mean, np.square)
