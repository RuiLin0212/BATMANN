import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable, Function
from torch.optim.lr_scheduler import StepLR
import torch.backends.cudnn as cudnn
import numpy as np
import os
import logging.config
import math
import argparse
import random
import time, datetime
import os
import shutil

from utils.mann import *
from utils.mann_approx import *
from data.dataset import *
from data.data_loading import *
from model.controller import *
from quant.XNOR_module import *

from gpueater.gpu_eater import occupy_gpus_mem

# argparse
parser = argparse.ArgumentParser('MANN for Few-Shot Learning')

# log path
parser.add_argument(
    '--log_dir',
    type=str,
    help='The path to store the training log file.')

# data path
parser.add_argument(
    '--data_dir',
    type=str,
    help='The path to the dataset, shold be a absolute path')

# controller structure
parser.add_argument(
    '--input_channel',
    type=int,
    default=1,
    help='The number of channels of the input.')

parser.add_argument(
    '--feature_dim',
    type=int,
    default=512,
    help='The dimension of the feature vectors generated by the controller.')

# m-way, n-shot problem
parser.add_argument(
    '--class_num',
    type=int,
    default=5,
    help='Number of classes used in the MANN training.')

parser.add_argument(
    '--num_shot',
    type=int,
    default=5,
    help='Number of samples per class.')

# data sampling for training data
parser.add_argument(
    '--pool_query_train',
    type=int,
    default=10,
    help='(Training phase) Number of samples that will be reserved for sampling queries')

parser.add_argument(
    '--pool_val_train',
    type=int,
    default=5,
    help='(Training phase) Number of samples that will be reserved for sampling validation samples')

parser.add_argument(
    '--batch_size_train',
    type=int,
    default=15,
    help='(Training phase) Number of queries per class.')

parser.add_argument(
    '--val_num_train',
    type=int,
    default=3,
    help='(Training phase) Number of samples used to do validation.')

# data sampling for testing data
parser.add_argument(
    '--pool_query_test',
    type=int,
    default=10,
    help='(Inference phase) Number of samples that will be reserved for sampling queries')

parser.add_argument(
    '--batch_size_test',
    type=int,
    default=15,
    help='(Inference phase) Number of queries per class.')

# episode & log interval
parser.add_argument(
    '--train_episode',
    type=int,
    default=1000,
    help='Number of episode to train the controller.')

parser.add_argument(
    '--log_interval',
    type=int,
    default=10,
    help='Intervals to print the training process.')

parser.add_argument(
    '--val_episode',
    type=int,
    default=250,
    help='Number of episode to validate the controller.')

parser.add_argument(
    '--val_interval',
    type=int,
    default=200,
    help='Intervals to validate the controller.')

parser.add_argument(
    '--test_episode',
    type=int,
    default=1000,
    help='Number of episode to test the mature controller.')

# optimizer
parser.add_argument(
    '--learning_rate',
    type=float,
    default=1e-3,
    help='Initial learning rate.')

# quantizatoin
parser.add_argument(
    '--quantization_learn',
    type=str,
    default='No',
    choices={'No', 'XNOR', 'RBNN'},
    help='Binarize the Controller or not.')

parser.add_argument(
    '--quantization_infer',
    type=int,
    default=0,
    choices={0, 1},
    help='Binarize the features or not.')

# RBNN setting
parser.add_argument(
    '--rotation_update',
    default=1,
    type=int,
    metavar='N',
    help='interval of updating rotation matrix (default:1)')

parser.add_argument(
    '--a32',
    default=1,
    type=int,
    choices={0, 1},
    help='w1a32')

# test pretrain or not
parser.add_argument(
    '--test_only',
    type=int,
    default=0,
    choices={0, 1},
    help='Use a pretrained Controller or not.')

parser.add_argument(
    '--pretrained_dir',
    type=str,
    default=None,
    help='The path to the pretrained ckpt.')

# choose the scheme to calculate similarity
parser.add_argument(
    '--sim_cal',
    type=str,
    default='softabs',
    choices={'cos_softabs', 'cos_softmax', 'dot_abs'},
    help='The scheme to calculate similarity.')

# binary or bipolar
parser.add_argument(
    '--binary_id',
    type=int,
    default=1,
    choices={1, 2},
    help='choose binary (binary-1, {-1, 1}) or bipolar (binary-2, {0, 1}).')

# resume
parser.add_argument(
    '--resume',
    action='store_true',
    help='whether continue training from the same directory', )

# gpu
parser.add_argument(
    '--gpu',
    type=str,
    default='0',
    help='Select gpu to use.')

# epsilon
parser.add_argument(
    '--epsilon',
    type=float)
    
# exp-id
parser.add_argument(
    '--exp_id',
    type=int)    

args = parser.parse_args()


# set up logger
def get_logger(file_path):
    logger = logging.getLogger('gal')
    log_format = '%(asctime)s | %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%m/%d %I:%M:%S %p')
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.INFO)

    return logger


# main
def main():
    cudnn.benchmark = True
    cudnn.enabled = True

    # make the log directory and log the args
    if not os.path.isdir(args.log_dir):
        os.makedirs(args.log_dir)
    now = datetime.datetime.now().strftime('%Y-%m-%d-%H:%M:%S')
    logger = get_logger(os.path.join(args.log_dir, 'logger' + now + '.log'))
    logger.info("args = %s", args)
    logger.info('-' * 50)

    # init the data folder ...
    logger.info("========> Initialize data folders...")
    # init character folders for dataset construction
    manntrain_character_folders, manntest_character_folders = omniglot_character_folders(data_path=args.data_dir)

    # init the controller ...
    logger.info("========> Build and Initialize the Controller...")
    controller = Controller(num_in_channels=args.input_channel, feature_dim=args.feature_dim,
                            quant=args.quantization_learn)
    logger.info(controller)
    controller.cuda()
    if len(args.gpu) > 1:
        device_id = []
        for i in range((len(args.gpu) + 1) // 2):
            device_id.append(i)
        controller = nn.DataParallel(controller, device_ids=device_id).cuda()

    if args.test_only == 0:
        # define the optimizer
        optimizer = torch.optim.Adam(controller.parameters(), lr=args.learning_rate)
        lr_scheduler = StepLR(optimizer, step_size=100000, gamma=0.5)

        # build graph
        logger.info("========> Training...")

        best_accuracy = 0.0

        # loss function
        criterion = nn.CrossEntropyLoss()
        criterion = criterion.cuda()

        total_rewards1 = 0
        start_episode = 0

        # resume
        if args.resume:
            logger.info('========> Loading checkpoint {} ...'.format(args.pretrained_dir))
            ckpt = torch.load(args.pretrained_dir)
            start_episode = ckpt['episode'] + 1
            best_accuracy = ckpt['best_acc']

            # deal with the single-multi GPU problem
            new_state_dic = OrderedDict()
            tmp_ckpt = ckpt['state_dict']
            if len(args.gpu) > 1:
                for k, v in tmp_ckpt.items():
                    new_state_dic['module.' + k.replace('module.', '')] = v
            else:
                for k, v in tmp_ckpt.items():
                    new_state_dic[k.replace('module.', '')] = v

            controller.load_state_dict(new_state_dic)
            logger.info('loaded checkpoint {} episode = {}', format(args.pretrained_dir, start_episode))

        ######################
        #     Train
        ######################
        episode = start_episode
        for episode in range(args.train_episode):

            # init dataset
            # sample_dataloader: obtain previous samples for compare
            # batch_dataloader: batch samples for training
            degrees = random.choice([0, 90, 180, 270])  # data augmentation
            task_train = OmniglotTask(manntrain_character_folders, args.class_num, args.num_shot, args.pool_query_train,
                                      val_num=args.pool_val_train)
            support_dataloader = get_data_loader(task_train, num_per_class=args.num_shot, split='train',
                                                 shuffle=False, rotation=degrees)
            query_dataloader = get_data_loader(task_train, num_per_class=args.batch_size_train, split='query',
                                               shuffle=True, rotation=degrees)
            val_dataloader = get_data_loader(task_train, num_per_class=args.val_num_train, split='val',
                                             shuffle=True,
                                             rotation=degrees)

            if (episode + 1) % args.val_interval != 0:
                del val_dataloader

            # sample data
            supports, supports_labels = support_dataloader.__iter__().next()
            queries, queries_labels = query_dataloader.__iter__().next()
            queries_labels = queries_labels.cuda()

            # calculate features
            supports_features = controller(Variable(supports).cuda())  # will be stored in the key memory
            queries_features = controller(Variable(queries).cuda())

            # quantization
            if args.quantization_learn == 'XNOR' or args.quantization_learn == 'RBNN':
                if args.binary_id == 1:
                    supports_features = torch.sign(supports_features)
                    queries_features = torch.sign(queries_features)
                elif args.binary_id == 2:
                    supports_features = torch.sign(supports_features)
                    supports_features = (supports_features + 1) / 2
                    queries_features = torch.sign(queries_features)
                    queries_features = (queries_features + 1) / 2

            # add(rewrite) memory-augmented memory
            kv_mem = KeyValueMemory(supports_features, supports_labels)
            kv = kv_mem.kv

            del support_dataloader, query_dataloader, supports, supports_labels, supports_features, queries

            # predict
            if args.sim_cal == 'cos_softabs':
                prediction1 = sim_comp(kv, queries_features)
            elif args.sim_cal == 'cos_softmax':
                prediction1 = sim_comp_softmax(kv, queries_features)

            del queries_features

            predict_labels1 = torch.argmax(prediction1.data, 1).cuda()
            rewards1 = [1 if predict_labels1[j] == queries_labels[j]
                        else 0 for j in range(args.class_num * args.batch_size_train)]
            total_rewards1 += np.sum(rewards1)
            loss = criterion(prediction1, queries_labels.cuda())

            # Update
            controller.zero_grad()
            loss.backward()
            optimizer.step()
            lr_scheduler.step()

            # log the training process
            if (episode + 1) % args.log_interval == 0:
                logger.info('episode:{}, loss:{:.2f}'.format(episode + 1, loss.item()))

            ######################
            #     Validation
            ######################
            if (episode + 1) % args.val_interval == 0:

                logger.info('-------- Validation --------')
                total_rewards2 = 0

                for i in range(args.val_episode):
                    degrees = random.choice([0, 90, 180, 270])

                    val_images, val_labels = val_dataloader.__iter__().next()
                    val_labels = val_labels.cuda()

                    # calculate features
                    val_features = controller(Variable(val_images).cuda())

                    del val_images

                    # quantization
                    if args.quantization_learn == 'XNOR' or args.quantization_learn == 'RBNN':
                        if args.binary_id == 1:
                            val_features = torch.sign(val_features)
                        elif args.binary_id == 2:
                            val_features = torch.sign(val_features)
                            val_features = (val_features + 1) / 2

                    # predict
                    if args.sim_cal == 'cos_softabs':
                        prediction2 = sim_comp(kv, val_features)
                    elif args.sim_cal == 'cos_softmax':
                        prediction2 = sim_comp_softmax(kv, val_features)

                    predict_labels2 = torch.argmax(prediction2.data, 1).cuda()

                    del val_features

                    rewards2 = [1 if predict_labels2[j] == val_labels[j]
                                else 0 for j in range(args.class_num * args.val_num_train)]
                    total_rewards2 += np.sum(rewards2)

                val_accuracy = total_rewards2 / 1.0 / (args.val_episode * args.class_num * args.val_num_train)
                logger.info('Validation accuracy: {:.2f}%.'.format(val_accuracy * 100))

                # save the best performance controller
                is_best = False
                if val_accuracy > best_accuracy:
                    is_best = True
                    best_accuracy = val_accuracy
                    logger.info('Save controller for episode: {}.'.format(episode + 1))
                logger.info('----------------------------')
                save_checkpoint({
                    'episode': episode,
                    'state_dict': controller.state_dict(),
                    'best_acc': best_accuracy,
                    'optimizer': optimizer.state_dict(),
                }, is_best, args.log_dir)

            del kv_mem

        train_accuracy = total_rewards1 / 1.0 / (args.train_episode * args.class_num * args.batch_size_train)
        logger.info(' ')
        logger.info('========> Training finished!')
        logger.info('Training accuracy: {:.2f}%.'.format(train_accuracy * 100))
        logger.info(' ')

    ######################
    #        Test
    ######################
    total_rewards3 = 0
    # define the optimizer
    optimizer = torch.optim.Adam(controller.parameters(), lr=args.learning_rate)
    lr_scheduler = StepLR(optimizer, step_size=100000, gamma=0.5)
    # loss function
    criterion = nn.CrossEntropyLoss().cuda()

    if args.test_only == 0:
        # Test (Training finished)
        logger.info('========> Use the best performance Controller to test...')
        ckpt = torch.load(os.path.join(args.log_dir, 'model_best.pth.tar'))
        controller.load_state_dict(ckpt['state_dict'])

    if args.test_only == 1:
        # Test (Use pretrained parameters)
        logger.info('========> Use a pretrained Controller to test...')
        ckpt = torch.load(args.pretrained_dir)
        controller.load_state_dict(ckpt['state_dict'])

    for i in range(args.test_episode):
        degrees = random.choice([0, 90, 180, 270])
        task_test = OmniglotTask(manntest_character_folders, args.class_num, args.num_shot, args.pool_query_test,
                                 val_num=0)
        support_dataloader2 = get_data_loader(task_test, num_per_class=args.num_shot, split='train', shuffle=False,
                                              rotation=degrees)  # support vectors for testing / validation
        query_dataloader2 = get_data_loader(task_test, num_per_class=args.batch_size_test, split='query', shuffle=True,
                                            rotation=degrees)  # queries for testing / validation
        supports_images2, supports_labels2 = support_dataloader2.__iter__().next()
        queries_images2, queries_labels2 = query_dataloader2.__iter__().next()
        queries_labels2 = queries_labels2.cuda()
        
        # grad
        queries_images2.requires_grad = True
        
        # calculate features
        supports_features2 = controller(supports_images2.cuda())
        queries_features2 = controller(queries_images2.cuda())
         
        # add(rewrite) memory-augmented memory
        kv_mem = KeyValueMemory(supports_features2, supports_labels2)
        kv = kv_mem.kv
        
        """ attack """
        # predict (approx)
        prediction3 = sim_comp_approx(kv, queries_features2, binary_id=args.binary_id)
        
        def fgsm_attack(image, epsilon, data_grad):
            # Collect the element-wise sign of the data gradient
            sign_data_grad = data_grad.sign()
            # Create the perturbed image by adjusting each pixel of the input image
            perturbed_image = image + epsilon * sign_data_grad
            # Adding clipping to maintain [0,1] range
            perturbed_image = torch.clamp(perturbed_image, 0, 1)
            # Return the perturbed image
            return perturbed_image
        loss = criterion(prediction3, queries_labels2.cuda())
        controller.zero_grad()
        loss.backward(retain_graph=True)
        data_grad = queries_images2.grad.data
        queries_images2 = fgsm_attack(queries_images2, args.epsilon, data_grad)
        queries_features2 = controller(Variable(queries_images2).cuda())
        """ end """
        
        ### t-sne for test only (after attack)
        ks_num = queries_features2.detach().cpu().numpy()
        vs_num = queries_labels2.detach().cpu().numpy()
        np.save('ks-exp' + str(args.exp_id) + '.npy', ks_num)
        np.save('vs-exp' + str(args.exp_id) + '.npy', vs_num)
        
        # quantization
        if args.quantization_infer == 1:
            if args.binary_id == 1:  # {-1, 1}
                supports_features2 = torch.sign(supports_features2)
                queries_features2 = torch.sign(queries_features2)
            elif args.binary_id == 2:  # {0, 1}
                supports_features2 = torch.sign(supports_features2)
                supports_features2 = (supports_features2 + 1) / 2
                queries_features2 = torch.sign(queries_features2)
                queries_features2 = (queries_features2 + 1) / 2
                
        # predict (approx)
        prediction3 = sim_comp_approx(kv, queries_features2, binary_id=args.binary_id)

        del support_dataloader2, query_dataloader2, supports_images2, supports_features2, queries_images2, queries_features2

        predict_labels3 = torch.argmax(prediction3.data, 1).cuda()
        rewards3 = [1 if predict_labels3[j] == queries_labels2[j]
                    else 0 for j in range(args.class_num * args.batch_size_test)]
        total_rewards3 += np.sum(rewards3)

        del kv_mem

    test_accuracy = total_rewards3 / 1.0 / (args.test_episode * args.class_num * args.batch_size_test)
    logger.info('Testing accuracy: {:.2f}%.'.format(test_accuracy * 100))


if __name__ == '__main__':

    # set gpus
    if args.gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

    # occury gpus mem
    occupy_gpus_mem()

    main()
