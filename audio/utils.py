import subprocess
import os

def reverse_sounds_in_patch(patch_dir):
    for f in os.scandir(patch_dir):
        name, ext = f.name.split('.')
        input = os.path.join(patch_dir, f.name)
        output = os.path.join(patch_dir, name + 'r.wav'
        cmd=f'ffmpeg -i {input} -af areverse {output}' 
        print(cmd)
        subprocess.run(cmd, shell=True)
        os.remove(input)
        
