import sys
import torch
import argparse
import os
import csv
import yaml
from torchvision.utils import save_image

from pathlib import Path
from IF_GMI.utils.attack_config_parser import AttackConfigParser

from IF_GMI.utils.stylegan import crop_and_resize
import wandb

class Tee(object):
    """A workaround method to print in console and write to log file
    """

    def __init__(self, name, mode):
        self.file = open(name, mode)
        self.stdout = sys.stdout
        sys.stdout = self

    def __del__(self):
        sys.stdout = self.stdout
        self.file.close()

    def write(self, data):
        if not '...' in data:
            self.file.write(data)
        self.stdout.write(data)

    def flush(self):
        self.file.flush()

def log_images(config, path, eval_model, label, layer_num, final_imgs, idx_to_class):
    # Logging of final images
    num_imgs = 4

    # num_imgs = min(4, )    
    
    eval_model.eval()

    # Log images
    for layer in range(layer_num):
        imgs_original = final_imgs[layer][:num_imgs]
        log_imgs = crop_and_resize(
            imgs_original, crop_size=config.attack_center_crop, resize=config.attack_resize).cpu()
        log_targets = torch.tensor([label for _ in range(num_imgs)])
        output = eval_model(log_imgs).cpu()
        log_predictions = torch.argmax(output, dim=1)
        confidences = output.softmax(1)
        
        # log_target_confidences = torch.gather(confidences, 1, log_targets.unsqueeze(1))
        log_target_confidences = torch.gather(confidences, 1, log_targets.unsqueeze(0))[0]
        
        log_max_confidences = torch.max(confidences, dim=1)[0]

        img_path = os.path.join(path, str(label), f'layer{layer}')
        Path(f"{img_path}").mkdir(parents=True, exist_ok=True)
        for i in range(num_imgs):
            title = f'pred{idx_to_class[log_predictions[i].item()]}_max{log_max_confidences[i].item():.2f}_target{log_target_confidences[i].item():.2f}.png'
            caption=os.path.join(img_path, title)
            save_image(log_imgs[i], caption, normalize=True)
        
        if wandb.run:
            log_final_images_wandb(log_imgs, log_predictions, log_max_confidences, log_target_confidences, idx_to_class)
    
def log_final_images_wandb(imgs, predictions, max_confidences, target_confidences, idx2cls):
    wand_imgs = [
        wandb.Image(
            img.permute(1, 2, 0).numpy(),
            caption=f'pred={idx2cls[pred.item()]} ({max_conf:.2f}), target_conf={target_conf:.2f}'
        ) for img, pred, max_conf, target_conf in zip(
            imgs.cpu(), predictions, max_confidences, target_confidences)
    ]
    wandb.log({'final_images': wand_imgs})

def create_parser():
    parser = argparse.ArgumentParser(
        description='Performing attack')
    parser.add_argument('-c',
                        '--config',
                        default=None,
                        type=str,
                        dest="config",
                        help='Config .json file path (default: None)')
    parser.add_argument('--no_rtpt',
                        action='store_false',
                        dest="rtpt",
                        help='Disable RTPT')
    return parser


def parse_arguments(parser):
    args = parser.parse_args()

    if not args.config:
        print(
            "Configuration file is missing. Please check the provided path. Execution is stopped."
        )
        exit()

    # Load attack config
    config = AttackConfigParser(args.config)

    return config, args


def create_initial_vectors(config, G, target_model, targets, device):
    with torch.no_grad():
        w = config.create_candidates(G, target_model, targets).cpu()
        if config.attack['single_w']:
            w = w[:, 0].unsqueeze(1)
    return w


def write_precision_list(filename, precision_list):
    filename = f"{filename}.csv"
    with open(filename, 'w', newline='') as csv_file:
        wr = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
        for row in precision_list:
            wr.writerow(row)
    return filename


def save_dict_to_yaml(dict_value: dict, save_path: str):
    with open(save_path, 'w') as file:
        file.write(yaml.dump(dict_value, allow_unicode=True))
