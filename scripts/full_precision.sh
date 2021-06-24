#python main.py \
#--log_dir ./log_full_precision \
#--data_dir /mnt/nfsdisk/jier/4_MANN/mann_hdv/data \
#--input_channel 1 \
#--feature_dim 512 \
#--class_num 20 \
#--num_shot 5 \
#--pool_query_train 10 \
#--pool_val_train 3 \
#--batch_size_train 4 \
#--val_num_train 3 \
#--pool_query_test 15 \
#--batch_size_test 4 \
#--train_episode 10000 \
#--log_interval 100 \
#--val_episode 250 \
#--val_interval 500 \
#--test_episode 1000 \
#--learning_rate 0.0001 \
#--quantization 0 \
#--test_only 0 \
#--pretrained_dir None \
#--gpu 0,1 

#CUDA_VISIBLE_DEVICES=0,1 python main.py \
#--log_dir ./log_full_precision_5_1 \
#--data_dir /mnt/nfsdisk/jier/4_MANN/mann_hdv/data \
#--input_channel 1 \
#--feature_dim 512 \
#--class_num 5 \
#--num_shot 1 \
#--pool_query_train 10 \
#--pool_val_train 9 \
#--batch_size_train 4 \
#--val_num_train 3 \
#--pool_query_test 15 \
#--batch_size_test 4 \
#--train_episode 10000 \
#--log_interval 100 \
#--val_episode 250 \
#--val_interval 500 \
#--test_episode 1000 \
#--learning_rate 0.0001 \
#--quantization 0 \
#--test_only 0 \
#--pretrained_dir None \
#--gpu 0,1

CUDA_VISIBLE_DEVICES=0,1,2,3 python main.py \
--log_dir ./log_full_precision_100_5 \
--data_dir /mnt/nfsdisk/jier/4_MANN/mann_hdv/data \
--input_channel 1 \
--feature_dim 512 \
--class_num 100 \
--num_shot 5 \
--pool_query_train 10 \
--pool_val_train 5 \
--batch_size_train 4 \
--val_num_train 3 \
--pool_query_test 15 \
--batch_size_test 4 \
--train_episode 10000 \
--log_interval 100 \
--val_episode 250 \
--val_interval 500 \
--test_episode 1000 \
--learning_rate 0.0001 \
--quantization 0 \
--test_only 0 \
--pretrained_dir None \
--gpu 0,1,2,3  \

  