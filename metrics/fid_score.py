'''
    Source: https://github.com/mseitzer/pytorch-fid
    Modified code to be compatible with our attack pipeline

    Copyright [2021] [Maximilian Seitzer]

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

'''

import numpy as np
import pytorch_fid.fid_score
import torch
from pytorch_fid.inception import InceptionV3

from IF_GMI.utils.stylegan import create_image

IMAGE_EXTENSIONS = ('bmp', 'jpg', 'jpeg', 'pgm', 'png', 'ppm',
                    'tif', 'tiff', 'webp')


class FID_Score:
    def __init__(self,layer_num,device,crop_size=None, batch_size=128, dims=2048, num_workers=8, gpu_devices=[]):
        self.batch_size = batch_size
        self.dims = dims
        self.num_workers = num_workers
        self.device = device
        self.crop_size = crop_size
        self.pred_arr_fake = {i:[] for i in range(layer_num)}
        self.pred_arr_gt = []

        block_idx = InceptionV3.BLOCK_INDEX_BY_DIM[self.dims]
        inception_model = InceptionV3([block_idx]).to(self.device)
        if len(gpu_devices) > 1:
            self.inception_model = torch.nn.DataParallel(
                inception_model, device_ids=gpu_devices)
        else:
            self.inception_model = inception_model
        self.inception_model.to(device)
    
    def set(self, dataset_1, dataset_2):
        self.dataset_1 = dataset_1
        self.dataset_2 = dataset_2
    
    # get fid score for certain layer
    def compute_fid(self, layer):
        pred_arr_gt = np.concatenate(self.pred_arr_gt, axis=0)
        mu1 = np.mean(pred_arr_gt, axis=0)
        sigma1 = np.cov(pred_arr_gt, rowvar=False)   
        
        pred_arr_fake = np.concatenate(self.pred_arr_fake[layer], axis=0)
        mu2 = np.mean(pred_arr_fake, axis=0)
        sigma2 = np.cov(pred_arr_fake, rowvar=False)     
        fid_value = pytorch_fid.fid_score.calculate_frechet_distance(
            mu1, sigma1, mu2, sigma2)
        return fid_value
        
        
    def get_preds(self, layer, rtpt=None):
        self.get_preds_for_dataset(self.dataset_1, rtpt)
        self.get_preds_for_dataset(self.dataset_2, layer, rtpt, fake=True)

    # calculate fid
    def get_preds_for_dataset(self, dataset, layer=None, rtpt=None, fake=False):
        self.inception_model.eval()
        dataloader = torch.utils.data.DataLoader(dataset,
                                                 batch_size=self.batch_size,
                                                 shuffle=False,
                                                 drop_last=False,
                                                 pin_memory=True,
                                                 num_workers=self.num_workers)
        pred_arr = np.empty((len(dataset), self.dims))
        start_idx = 0
        max_iter = int(len(dataset) / self.batch_size)
        for step, (x, y) in enumerate(dataloader):
            with torch.no_grad():
                # inversion results
                if fake:
                    x = create_image(x, crop_size=self.crop_size, resize=299)
                x = x.to(self.device)
                pred = self.inception_model(x)[0]
            pred = pred.squeeze(3).squeeze(2).cpu().numpy()
            pred_arr[start_idx:start_idx + pred.shape[0]] = pred
            start_idx = start_idx + pred.shape[0]

            if rtpt:
                rtpt.step(
                    subtitle=f'FID Score Computation step {step} of {max_iter}')
        if fake:
            self.pred_arr_fake[layer].append(pred_arr)
        else:
            self.pred_arr_gt.append(pred_arr)
