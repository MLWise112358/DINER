import matplotlib.pyplot as plt
import numpy as np
import os
import torch
from torch import optim, nn
from model import Siren,MLP,DinerMLP,DinerSiren
from dataio import ImageData,ImageData_linear
from skimage import io
import skimage
import configargparse
from tensorboardX import SummaryWriter, writer
import time
import utils
from sklearn.preprocessing import normalize
from tqdm.autonotebook import tqdm
from torch.utils.data import DataLoader
from opt import HyperParameters


class Logger:
    filename = None
    
    @staticmethod
    def write(text):
        with open(Logger.filename, 'a') as log_file:
            log_file.write(text + '\n')
    
    @staticmethod
    def write_file(text):
        with open(Logger.filename, 'a') as log_file:
            log_file.write(text + '\n')


def relative_l2_loss(output,targets):
    output = (output + 1) / 2.
    targets = (targets + 1) / 2.
    relative_l2_error = (output - targets.to(output.dtype))**2 / (output.detach()**2 + 0.01)
    loss = relative_l2_error.mean()
    return loss


def train_img(opt):
    img_path                =       opt.img_path
    steps                   =       opt.steps
    lr                      =       opt.lr
    hidden_layers           =       opt.hidden_layers
    hidden_features         =       opt.hidden_features
    sidelength              =       opt.sidelength
    grayscale               =       opt.grayscale
    first_omega_0           =       opt.w0
    hidden_omega_0          =       opt.w0
    model_type              =       opt.model_type
    steps_til_summary       =       opt.steps_til_summary
    input_dim               =       opt.input_dim
    epochs                  =       opt.epochs
    remain_raw_resolution   =       opt.remain_raw_resolution
    experiment_name         =       opt.experiment_name

    # make directory
    log_dir = "log"
    utils.cond_mkdir(os.path.join(log_dir,experiment_name))

    # check parameters
    if steps % steps_til_summary:
        raise ValueError("steps_til_summary could not be devided by steps!")

    # logger
    Logger.filename = os.path.join(log_dir, experiment_name,'log.txt')

    device = torch.device('cuda')
    criteon = nn.MSELoss()

    out_features = 3

    Dataset = ImageData_linear(image_path = img_path,
                               sidelength = sidelength,
                               grayscale = grayscale,
                               remain_raw_resolution = remain_raw_resolution)
    model_input,gt = Dataset[0]


    model_input = model_input.to(device)
    gt = gt.to(device)

    hash_table_length = model_input.shape[0]

    if model_type == 'Siren':
        model = Siren(in_features = input_dim,
                          hidden_features = hidden_features,
                          hidden_layers = hidden_layers,
                          out_features = out_features,
                          ).to(device = device)

    
    elif model_type == 'MLP':
        model = MLP(in_features = input_dim,
                    out_features = out_features,
                    hidden_layers = hidden_layers,
                    hidden_features= hidden_features,
                    ).to(device = device)


    elif model_type == 'DinerSiren':
        model = DinerSiren(
                      hash_table_length = hash_table_length,
                      in_features = input_dim,
                      hidden_features = hidden_features,
                      hidden_layers = hidden_layers,
                      out_features = out_features,
                      outermost_linear = True,
                      first_omega_0 = first_omega_0,
                      hidden_omega_0 = hidden_omega_0).to(device = device)

    elif model_type == 'DinerMLP':
        model = DinerMLP(
                        hash_table_length = hash_table_length, 
                        in_features = input_dim, 
                        hidden_features = hidden_features,
                        hidden_layers = hidden_layers,
                        out_features = out_features).to(device = device)

    else:
        raise NotImplementedError("Model type not supported!")
        
    optimizer = optim.Adam(lr = lr,params = model.parameters())


    # training process
    with tqdm(total=epochs) as pbar:
        max_psnr = 0
        time_cost = 0
        for epoch in range(epochs):
            time_start = time.time()

            loss_relative = 0
            loss_mse = 0
            model_output = model(model_input)

            # loss = criteon(model_output,gt)

            loss_relative = relative_l2_loss(model_output,gt)
            loss_mse = criteon(model_output,gt)

            optimizer.zero_grad()
            loss_relative.backward()
            optimizer.step()

            torch.cuda.synchronize()
            time_cost += time.time() - time_start

            cur_psnr = utils.loss2psnr(loss_mse)
            max_psnr = max(max_psnr,cur_psnr)

            if (epochs + 1) % steps_til_summary == 0:
                log_str = f"[TRAIN] Epoch: {epoch+1} Loss: {loss_mse.item()} PSNR: {cur_psnr} Time: {round(time_cost, 2)}"
                Logger.write(log_str)

            pbar.update(1)
            
    utils.render_raw_image(model,os.path.join(log_dir,experiment_name,'recon.png'),[1200,1200],linear = True)

    recon_psnr = utils.calculate_psnr(os.path.join(log_dir,experiment_name,'recon.png'),img_path)

    print(f"Reconstruction PSNR: {recon_psnr:.2f}")

    return time_cost

if __name__ == "__main__":

    opt = HyperParameters()
    train_img(opt)

    # log_dir = 'log'
    # time_logger = np.zeros((10,30))
    # opt = HyperParameters()
    # for i in range(1,11):
    #     opt.input_dim = i
    #     for pic_idx in range(1,31):
    #         opt.img_path = f'pic/RGB_OR_1200x1200_{pic_idx:03d}.png'
    #         time_logger[i-1,pic_idx-1] = train_img(opt)

    # utils.save_data(time_logger,os.path.join(log_dir,opt.experiment_name,'time.mat'))
    # utils.save_data(time_logger,os.path.join(log_dir,opt.experiment_name,'time.npy'))


