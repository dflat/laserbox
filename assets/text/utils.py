import subprocess
import os
from TTS import simple

print(simple.keys())

def resample(dirpath, outdir, new_sr=22050, to_mono=True, remove=True, force=False):
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    for f in os.scandir(dirpath):
        name, ext = f.name.split('.')
        input = os.path.join(dirpath, f.name)
        #mono_suffix = '_mono' if to_mono else ''
        #output = os.path.join(outdir, name + f'_{new_sr}{mono_suffix}.wav')
        output = os.path.join(outdir, name + f'.wav')

        new_sr_option = f' -ar {new_sr} ' if new_sr else ''
        mono_option = ' -ac 1 ' if to_mono else ''
        force_option = ' -y ' if force else ''
        cmd=f'ffmpeg -i {input} {force_option}{new_sr_option}{mono_option} {output}'
        print(cmd)

        subprocess.run(cmd, shell=True)
        if remove:
            os.remove(input)
        

def make_tts(key, word_map=simple, to_wav=True):
    patch_name = key
    path = os.path.join("../sounds/patches/", patch_name)
    if not os.path.exists(path):
        os.makedirs(path)
    for name, word in word_map[key].items():
        file = os.path.join(path, name)
        cmd = f"say {word} -o {file}.aiff"
        subprocess.run(cmd, shell=True)
        if to_wav:
            ff_cmd = f'ffmpeg -i {file}.aiff -y {file}.wav' 
            subprocess.run(ff_cmd, shell=True)
            os.remove(f"{file}.aiff")

def reverse_sounds_in_patch(patch_dir):
    for f in os.scandir(patch_dir):
        name, ext = f.name.split('.')
        input = os.path.join(patch_dir, f.name)
        output = os.path.join(patch_dir, name + 'r.wav')
        cmd=f'ffmpeg -i {input} -af areverse {output}' 
        print(cmd)
        subprocess.run(cmd, shell=True)
        os.remove(input)
        
