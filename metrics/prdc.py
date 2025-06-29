
import sys

import numpy as np
import torch
from pytorch_fid.inception import InceptionV3

from IF_GMI.utils.stylegan import crop_and_resize
from IF_GMI.datasets.custom_subset import SingleClassSubset

sys.path.insert(0, '/workspace')


class PRDC:
    def __init__(self, layer_num, device, crop_size=None, batch_size=128, dims=2048, num_workers=16, gpu_devices=[]):
        self.batch_size = batch_size
        self.dims = dims
        self.num_workers = num_workers
        self.device = device
        self.crop_size = crop_size
        self.precision_list = {i: [] for i in range(layer_num)}
        self.recall_list = {i: [] for i in range(layer_num)}
        self.density_list = {i: [] for i in range(layer_num)}
        self.coverage_list = {i: [] for i in range(layer_num)}

        block_idx = InceptionV3.BLOCK_INDEX_BY_DIM[self.dims]
        inception_model = InceptionV3([block_idx])
        if len(gpu_devices) > 1:
            self.inception_model = torch.nn.DataParallel(
                inception_model, device_ids=gpu_devices)
        else:
            self.inception_model = inception_model
        self.inception_model.to(self.device)

    def set(self, dataset_real, dataset_fake):
        self.dataset_real = dataset_real
        self.dataset_fake = dataset_fake

    def get_prdc(self, layer):
        # Compute mean over targets
        # precision_list = torch.cat(self.precision_list[layer], dim=0)
        # recall_list = torch.cat(self.recall_list[layer], dim=0)
        # density_list = torch.cat(self.density_list[layer], dim=0)
        # coverage_list = torch.cat(self.coverage_list[layer], dim=0)

        precision = np.mean(self.precision_list[layer])
        recall = np.mean(self.recall_list[layer])
        density = np.mean(self.density_list[layer])
        coverage = np.mean(self.coverage_list[layer])
        return precision, recall, density, coverage

    def compute_metric(self, layer, cls, k=3, rtpt=None):
        with torch.no_grad():
            embedding_fake = self.compute_embedding(
                self.dataset_fake, cls, fake=True)
            embedding_real = self.compute_embedding(self.dataset_real, cls)

            pair_dist_real = torch.cdist(
                embedding_real, embedding_real, p=2)
            pair_dist_real = torch.sort(
                pair_dist_real, dim=1, descending=False)[0]
            pair_dist_fake = torch.cdist(
                embedding_fake, embedding_fake, p=2)
            pair_dist_fake = torch.sort(
                pair_dist_fake, dim=1, descending=False)[0]
            radius_real = pair_dist_real[:, k]
            radius_fake = pair_dist_fake[:, k]

            # Compute precision
            distances_fake_to_real = torch.cdist(
                embedding_fake, embedding_real, p=2)
            min_dist_fake_to_real, nn_real = distances_fake_to_real.min(
                dim=1)
            precision = (min_dist_fake_to_real <=
                            radius_real[nn_real]).float().mean()

            # Compute recall
            distances_real_to_fake = torch.cdist(
                embedding_real, embedding_fake, p=2)
            min_dist_real_to_fake, nn_fake = distances_real_to_fake.min(
                dim=1)
            recall = (min_dist_real_to_fake <=
                        radius_fake[nn_fake]).float().mean()

            # Compute density
            num_samples = distances_fake_to_real.shape[0]
            sphere_counter = (distances_fake_to_real <= radius_real.repeat(
                num_samples, 1)).float().sum(dim=0).mean()
            density = sphere_counter / k

            # Compute coverage
            num_neighbors = (distances_fake_to_real <= radius_real.repeat(
                num_samples, 1)).float().sum(dim=0)
            coverage = (num_neighbors > 0).float().mean()
            # Update rtpt
            if rtpt:
                rtpt.step(
                    subtitle=f'PRCD Computation of {cls}')

        self.precision_list[layer].append(precision.cpu().item())
        self.recall_list[layer].append(recall.cpu().item())
        self.density_list[layer].append(density.cpu().item())
        self.coverage_list[layer].append(coverage.cpu().item())

    def compute_embedding(self, dataset, cls=None, fake=False):
        self.inception_model.eval()
        if cls is not None:
            dataset = SingleClassSubset(dataset, cls)
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
                if fake:
                    x = crop_and_resize(x, crop_size=self.crop_size, resize=299)

                x = x.to(self.device)
                pred = self.inception_model(x)[0]
            pred = pred.squeeze(3).squeeze(2).cpu().numpy()
            pred_arr[start_idx:start_idx + pred.shape[0]] = pred
            start_idx = start_idx + pred.shape[0]

        return torch.from_numpy(pred_arr)
