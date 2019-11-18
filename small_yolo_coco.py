

import argparse
import os
import sys

##############################################

parser = argparse.ArgumentParser()
parser.add_argument('--epochs', type=int, default=10)
parser.add_argument('--batch_size', type=int, default=8)
parser.add_argument('--lr', type=float, default=1e-3)
parser.add_argument('--eps', type=float, default=1.)
parser.add_argument('--gpu', type=int, default=0)
parser.add_argument('--name', type=str, default='yolo_coco')
args = parser.parse_args()

if args.gpu >= 0:
    os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"]=str(args.gpu)

##############################################

import keras
import tensorflow as tf
import numpy as np
np.set_printoptions(threshold=10000)
import cv2

from bc_utils.conv_utils import conv_output_length
from bc_utils.conv_utils import conv_input_length

from bc_utils.init_tensor import init_filters
from bc_utils.init_tensor import init_matrix

from LoadCOCO import LoadCOCO
from yolo_loss import yolo_loss
from draw_boxes import draw_boxes

from collections import deque

##############################################

def write(text):
    print (text)
    f = open(args.name + '.results', "a")
    f.write(text + "\n")
    f.close()

##############################################

loader = LoadCOCO(batch_size=args.batch_size)
weights = np.load('small_yolo_weights.npy', allow_pickle=True).item()

###############################################################

def max_pool(x, s):
    return tf.nn.max_pool(x, ksize=[1,s,s,1], strides=[1,s,s,1], padding='SAME')

def conv(x, f, p, w, name):
    fw, fh, fi, fo = f

    trainable = (w == None)

    if w is not None:
        print ('loading %s | trainable %d ' % (name, trainable))
        filters_np = w[name]
        bias_np    = w[name + '_bias']
    else:
        print ('making %s | trainable %d ' % (name, trainable))
        filters_np = init_filters(size=[fw, fh, fi, fo], init='glorot_uniform')
        bias_np    = np.zeros(shape=fo)

    if not (np.shape(filters_np) == f):
        print (np.shape(filters_np), f)
        assert(np.shape(filters_np) == f)

    filters = tf.Variable(filters_np, dtype=tf.float32, trainable=trainable)
    bias    = tf.Variable(bias_np,    dtype=tf.float32, trainable=trainable)

    conv = tf.nn.conv2d(x, filters, [1,p,p,1], 'SAME') + bias
    relu = tf.nn.leaky_relu(conv, 0.1)

    return relu

def dense(x, size, w, name):
    input_size, output_size = size

    trainable = (w == None)

    if w is not None:
        print ('loading %s | trainable %d ' % (name, trainable))
        weights_np = w[name]
        bias_np    = w[name + '_bias']
    else:
        print ('making %s | trainable %d ' % (name, trainable))
        weights_np = init_matrix(size=size, init='glorot_uniform')
        bias_np    = np.zeros(shape=output_size)

    w = tf.Variable(weights_np, dtype=tf.float32, trainable=trainable)
    b  = tf.Variable(bias_np, dtype=tf.float32, trainable=trainable)

    out = tf.matmul(x, w) + b
    return out

###############################################################

image_ph  = tf.placeholder(tf.float32, [args.batch_size, 448, 448, 3])
coord_ph = tf.placeholder(tf.float32, [args.batch_size, None, 7, 7, 5])
obj_ph    = tf.placeholder(tf.float32, [args.batch_size, None, 7, 7])
no_obj_ph = tf.placeholder(tf.float32, [args.batch_size, None, 7, 7])
cat_ph    = tf.placeholder(tf.int32,   [args.batch_size, None, 7, 7])
vld_ph    = tf.placeholder(tf.float32, [args.batch_size, None, 7, 7])

lr_ph = tf.placeholder(tf.float32, ())

###############################################################

x = (image_ph / 255.0) * 2.0 - 1.0                                # 448

conv1 = conv(x, (7,7,3,64), 2, weights, 'conv_1')                 # 448
pool1 = max_pool(conv1, 2)                                        # 224
conv2 = conv(pool1, (3,3,64,192), 1, weights, 'conv_2')           # 112
pool2 = max_pool(conv2, 2)                                        # 112

conv3 = conv(pool2, (1,1,192,128), 1, weights, 'conv_3')          # 56
conv4 = conv(conv3, (3,3,128,256), 1, weights, 'conv_4')          # 56
conv5 = conv(conv4, (1,1,256,256), 1, weights, 'conv_5')          # 56
conv6 = conv(conv5, (3,3,256,512), 1, weights, 'conv_6')          # 56
pool3 = max_pool(conv6, 2)                                        # 56

conv7 = conv(pool3,   (1,1,512,256),  1, weights, 'conv_7')       # 28
conv8 = conv(conv7,   (3,3,256,512),  1, weights, 'conv_8')       # 28
conv9 = conv(conv8,   (1,1,512,256),  1, weights, 'conv_9')       # 28
conv10 = conv(conv9,  (3,3,256,512),  1, weights, 'conv_10')      # 28
conv11 = conv(conv10, (1,1,512,256),  1, weights, 'conv_11')      # 28
conv12 = conv(conv11, (3,3,256,512),  1, weights, 'conv_12')      # 28
conv13 = conv(conv12, (1,1,512,256),  1, weights, 'conv_13')      # 28
conv14 = conv(conv13, (3,3,256,512),  1, weights, 'conv_14')      # 28
conv15 = conv(conv14, (1,1,512,512),  1, weights, 'conv_15')      # 28
conv16 = conv(conv15, (3,3,512,1024), 1, weights, 'conv_16')      # 28
pool4 = max_pool(conv16, 2)                                       # 28

conv17 = conv(pool4,  (1,1,1024,512), 1, weights, 'conv_17')      # 14
conv18 = conv(conv17, (3,3,512,1024), 1, weights, 'conv_18')      # 14
conv19 = conv(conv18, (1,1,1024,512), 1, weights, 'conv_19')      # 14
conv20 = conv(conv19, (3,3,512,1024), 1, weights, 'conv_20')      # 14

conv21 = conv(conv20, (3,3,1024,1024), 1, None, 'conv_21')     # 14
conv22 = conv(conv21, (3,3,1024,1024), 2, None, 'conv_22')     # 14
conv23 = conv(conv22, (3,3,1024,1024), 1, None, 'conv_23')     # 7
conv24 = conv(conv23, (3,3,1024,1024), 1, None, 'conv_24')     # 7

flat = tf.reshape(conv24, [args.batch_size, 7*7*1024])

dense1 = tf.nn.relu(dense(flat,   (7*7*1024,   4096), None, 'dense_1'))
dense2 =            dense(dense1, (    4096, 7*7*90), None, 'dense_2')

out = tf.reshape(dense2, [args.batch_size, 7, 7, 90])

###############################################################

loss = yolo_loss(out, coord_ph, obj_ph, no_obj_ph, cat_ph, vld_ph)
train = tf.train.AdamOptimizer(learning_rate=lr_ph, epsilon=args.eps).minimize(loss)

###############################################################

config = tf.ConfigProto(allow_soft_placement=True)
config.gpu_options.allow_growth=True
sess = tf.Session(config=config)
sess.run(tf.global_variables_initializer())

###############################################################

counter = 0
losses = deque(maxlen=1000)

preds = deque(maxlen=100)
coords = deque(maxlen=100)
objs = deque(maxlen=100)
no_objs = deque(maxlen=100)
cats = deque(maxlen=100)
vlds = deque(maxlen=100)

###############################################################

while True:
    if not loader.empty():
        image, det = loader.pop()
        coord, obj, no_obj, cat, vld = det

        # wtf why is this not triggering ? 
        '''
        if (np.any(coord < 0.) or np.any(coord > 1.1)):
            print (coord)
            assert(not (np.any(coord < 0.) or np.any(coord > 1.1)))
        '''    

        lr = 1e-3 if counter < 50000 else 1e-2

        [out_np, loss_np, _] = sess.run([out, loss, train], feed_dict={image_ph: image, coord_ph: coord, obj_ph: obj, no_obj_ph: no_obj, cat_ph: cat, vld_ph: vld, lr_ph: lr})

        assert(not np.any(np.isnan(image)))
        assert(not np.any(np.isnan(out_np)))

        losses.append(loss_np)
        preds.append(out_np)
        coords.append(coord)
        objs.append(obj)
        no_objs.append(no_obj)
        cats.append(cat)
        vlds.append(vld)
        counter = counter + 1

        ################################################

        if (counter % 100 == 0):
            write('%d: lr %f loss %f' % (counter, lr, np.average(losses)))
            np.save('predictions', preds)
            np.save('labels', preds)


###############################################################



    
    
    
    
    
    


