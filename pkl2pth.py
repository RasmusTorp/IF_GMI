import pickle
import torch
import sys

def change(path, name):
    sys.path.append('IF_GMI/stylegan2_intermediate')
    with open(path, 'rb') as f:
        G = pickle.load(f)['G_ema']
        torch.save({'state_dict': G.state_dict()}, name)


if __name__ == '__main__':
    # modify the source .pkl to .pth
    model_name = "ffhq"
    path = f'stylegan2-ada-pytorch/{model_name}.pkl'
    name = f'stylegan2-ada-pytorch/{model_name}.pth'
    change(path=path, name=name)
