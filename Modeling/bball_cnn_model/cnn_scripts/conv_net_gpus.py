"""
Sample code for
Convolutional Neural Networks for Sentence Classification
http://arxiv.org/pdf/1408.5882v2.pdf

Much of the code is modified from
- deeplearning.net (for ConvNet classes)
- https://github.com/mdenil/dropout (for dropout)
- https://groups.google.com/forum/#!topic/pylearn-dev/3QbKtCumAW4 (for Adadelta)
"""
import cPickle
import numpy as np
from collections import defaultdict, OrderedDict
import theano
from theano import function, config, shared, sandbox
import theano.sandbox.cuda.basic_ops
import theano.tensor as T
from theano import config, shared, sandbox
import numpy
import re
import warnings
import sys
import time
import datetime
warnings.filterwarnings("ignore")

# Log Writing
def log_write(log_string):
    f_log = open('conv_net_log.txt','a')
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    print (timestamp + ': ' + log_string)
    f_log.write(timestamp + ': ' + log_string + '\n')
    f_log.close()

f_log = open('conv_net_log.txt','w')
timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
f_log.write(timestamp + ': ' + 'Running' + '\n')
f_log.close()

#different non-linearities
def ReLU(x):
    y = T.maximum(0.0, x)
    return(y)
def Sigmoid(x):
    y = T.nnet.sigmoid(x)
    return(y)
def Tanh(x):
    y = T.tanh(x)
    return(y)
def Iden(x):
    y = x
    return(y)

def train_conv_net(datasets,
                   U,
                   img_w,
                   filter_hs,
                   hidden_units,
                   dropout_rate=[0.5],
                   shuffle_batch=True,
                   n_epochs=10,
                   batch_size=50,
                   lr_decay = 0.95,
                   conv_non_linear="relu",
                   activations=[Iden],
                   sqr_norm_lim=9,
                   non_static=True):
    """
    Train a simple conv net
    img_h = sentence length (padded where necessary)
    img_w = word vector length
    filter_hs = filter window sizes
    hidden_units = [x,y] x is the number of feature maps (per filter window), and y is the penultimate layer
    sqr_norm_lim = s^2 in the paper
    lr_decay = adadelta decay parameter
    """
    rng = np.random.RandomState(3435)
    img_h = len(datasets[0][0])-1
    filter_w = img_w
    feature_maps = hidden_units[0]
    filter_shapes = []
    pool_sizes = []
    for filter_h in filter_hs:
        filter_shapes.append((feature_maps, 1, filter_h, filter_w))
        pool_sizes.append((img_h-filter_h+1, img_w-filter_w+1))
    parameters = [("image shape",img_h,img_w),("filter shape",filter_shapes), ("hidden_units",hidden_units),
                  ("dropout", dropout_rate), ("batch_size",batch_size),("non_static", non_static),
                    ("learn_decay",lr_decay), ("conv_non_linear", conv_non_linear), ("non_static", non_static)
                    ,("sqr_norm_lim",sqr_norm_lim),("shuffle_batch",shuffle_batch)]
    log_write(str(parameters))

    #define model architecture
    index = T.lscalar()
    x = T.matrix('x')
    y = T.ivector('y')
    Words = theano.shared(value = U, name = "Words")
    zero_vec_tensor = T.vector()
    zero_vec = np.asarray(np.zeros(img_w),"float32")
    set_zero = theano.function([zero_vec_tensor], updates=[(Words, T.set_subtensor(Words[0,:], zero_vec_tensor))]) #, allow_input_downcast=True
    layer0_input = Words[T.cast(x.flatten(),dtype="int32")].reshape((x.shape[0],1,x.shape[1],Words.shape[1]))
    conv_layers = []
    layer1_inputs = []
    for i in xrange(len(filter_hs)):
        filter_shape = filter_shapes[i]
        pool_size = pool_sizes[i]
        conv_layer = LeNetConvPoolLayer(rng, input=layer0_input, lnum=i, image_shape=(batch_size, 1, img_h, img_w),
                                filter_shape=filter_shape, poolsize=pool_size, non_linear=conv_non_linear)
        layer1_input = conv_layer.output.flatten(2)
        conv_layers.append(conv_layer)
        layer1_inputs.append(layer1_input)
    layer1_input = T.concatenate(layer1_inputs,1)
    hidden_units[0] = feature_maps*len(filter_hs)
    classifier = MLPDropout(rng, input=layer1_input, layer_sizes=hidden_units, activations=activations, dropout_rates=dropout_rate)

    #define parameters of the model and update functions using adadelta
    params = classifier.params
    for conv_layer in conv_layers:
        params += conv_layer.params
    if non_static:
        #if word vectors are allowed to change, add them as model parameters
        params += [Words]
    cost = classifier.negative_log_likelihood(y)
    dropout_cost = classifier.dropout_negative_log_likelihood(y)
    grad_updates = sgd_updates_adadelta(params, dropout_cost, lr_decay, 1e-6, sqr_norm_lim)

    #shuffle dataset and assign to mini batches. if dataset size is not a multiple of mini batches, replicate
    #extra data (at random)
    np.random.seed(3455)
    if datasets[0].shape[0] % batch_size > 0:
        extra_data_num = batch_size - datasets[0].shape[0] % batch_size
        train_set = np.random.permutation(datasets[0])
        extra_data = train_set[:extra_data_num]
        new_data=np.append(datasets[0],extra_data,axis=0)
    else:
        new_data = datasets[0]
    new_data = np.random.permutation(new_data)
    n_batches = new_data.shape[0]/batch_size
    n_train_batches = int(np.round(n_batches*0.9))

    #divide train set into train/val sets
    test_set_x = np.asarray(datasets[1][:,:img_h],"float32")
    test_set_y = np.asarray(datasets[1][:,-1],"int32")
    train_set = new_data[:n_train_batches*batch_size,:]
    val_set = new_data[n_train_batches*batch_size:,:]
    train_set_x, train_set_y = shared_dataset((train_set[:,:img_h],train_set[:,-1]))
    val_set_x, val_set_y = shared_dataset((val_set[:,:img_h],val_set[:,-1]))
    n_val_batches = n_batches - n_train_batches
    val_model = theano.function([index], sandbox.cuda.basic_ops.gpu_from_host(T.cast(classifier.errors(y),'float32')),
         givens={
            x: val_set_x[index * batch_size: (index + 1) * batch_size],
            y: val_set_y[index * batch_size: (index + 1) * batch_size]})

    #compile theano functions to get train/val/test errors
    test_model = theano.function([index], sandbox.cuda.basic_ops.gpu_from_host(T.cast(classifier.errors(y),'float32')),
             givens={
                x: train_set_x[index * batch_size: (index + 1) * batch_size],
                y: train_set_y[index * batch_size: (index + 1) * batch_size]})
    train_model = theano.function([index], sandbox.cuda.basic_ops.gpu_from_host(cost), updates=grad_updates,
          givens={
            x: train_set_x[index*batch_size:(index+1)*batch_size],
            y: train_set_y[index*batch_size:(index+1)*batch_size]})
    test_pred_layers = []
    test_size = test_set_x.shape[0]
    test_layer0_input = Words[T.cast(x.flatten(),dtype="int32")].reshape((test_size,1,img_h,Words.shape[1]))
    for conv_layer in conv_layers:
        test_layer0_output = conv_layer.predict(test_layer0_input, test_size)
        test_pred_layers.append(test_layer0_output.flatten(2))
    test_layer1_input = T.concatenate(test_pred_layers, 1)
    test_y_pred = classifier.predict(test_layer1_input)
    test_error = T.mean(T.neq(test_y_pred, y))
    test_model_all = theano.function([x,y], sandbox.cuda.basic_ops.gpu_from_host(T.cast(test_error,'float32')))

    #start training over mini-batches
    log_write('... training')
    epoch = 0
    best_val_perf = 0
    val_perf = 0
    test_perf = 0
    cost_epoch = 0
    while (epoch < n_epochs):
        epoch = epoch + 1
        if shuffle_batch:
            for minibatch_index in np.random.permutation(range(n_train_batches)):
                cost_epoch = numpy.asarray(train_model(minibatch_index))
                set_zero(zero_vec)
        else:
            for minibatch_index in xrange(n_train_batches):
                cost_epoch = numpy.asarray(train_model(minibatch_index))
                set_zero(zero_vec)
        train_losses = [numpy.asarray(test_model(i)) for i in xrange(n_train_batches)]
        train_perf = 1 - np.mean(train_losses)
        val_losses = [numpy.asarray(val_model(i)) for i in xrange(n_val_batches)]
        val_perf = 1- np.mean(val_losses)
        log_write('epoch %i, train perf %f %%, val perf %f' % (epoch, train_perf * 100., val_perf*100.))

        if val_perf >= best_val_perf:
            best_val_perf = val_perf
            #test_loss = numpy.asarray(test_model_all(test_set_x,test_set_y))
            #test_perf = 1 - test_loss

    #saving model
    with open('cnn_model.pickle', 'wb') as f_model_out:
        cPickle.dump(classifier.params, f_model_out, -1)
    return test_perf

def shared_dataset(data_xy, borrow=True):
        """ Function that loads the dataset into shared variables

        The reason we store our dataset in shared variables is to allow
        Theano to copy it into the GPU memory (when code is run on GPU).
        Since copying data into the GPU is slow, copying a minibatch everytime
        is needed (the default behaviour if the data is not in a shared
        variable) would lead to a large decrease in performance.
        """
        data_x, data_y = data_xy
        shared_x = theano.shared(np.asarray(data_x,
                                               dtype=theano.config.floatX),
                                 borrow=borrow)
        shared_y = theano.shared(np.asarray(data_y,
                                               dtype=theano.config.floatX),
                                 borrow=borrow)
        return shared_x, T.cast(shared_y, 'int32')

def sgd_updates_adadelta(params,cost,rho=0.95,epsilon=1e-6,norm_lim=9,word_vec_name='Words'):
    """
    adadelta update rule, mostly from
    https://groups.google.com/forum/#!topic/pylearn-dev/3QbKtCumAW4 (for Adadelta)
    """
    updates = OrderedDict({})
    exp_sqr_grads = OrderedDict({})
    exp_sqr_ups = OrderedDict({})
    gparams = []
    for param in params:
        empty = np.zeros_like(param.get_value())
        exp_sqr_grads[param] = theano.shared(value=as_floatX(empty),name="exp_grad_%s" % param.name)
        gp = T.grad(cost, param)
        exp_sqr_ups[param] = theano.shared(value=as_floatX(empty), name="exp_grad_%s" % param.name)
        gparams.append(gp)
    for param, gp in zip(params, gparams):
        exp_sg = exp_sqr_grads[param]
        exp_su = exp_sqr_ups[param]
        up_exp_sg = rho * exp_sg + (1 - rho) * T.sqr(gp)
        updates[exp_sg] = up_exp_sg
        step =  -(T.sqrt(exp_su + epsilon) / T.sqrt(up_exp_sg + epsilon)) * gp
        updates[exp_su] = rho * exp_su + (1 - rho) * T.sqr(step)
        stepped_param = param + step
        if (param.get_value(borrow=True).ndim == 2) and (param.name!='Words'):
            col_norms = T.sqrt(T.sum(T.sqr(stepped_param), axis=0))
            desired_norms = T.clip(col_norms, 0, T.sqrt(norm_lim))
            scale = desired_norms / (1e-7 + col_norms)
            updates[param] = stepped_param * scale
        else:
            updates[param] = stepped_param
    return updates

def as_floatX(variable):
    if isinstance(variable, float):
        return np.cast[theano.config.floatX](variable)

    if isinstance(variable, np.ndarray):
        return np.cast[theano.config.floatX](variable)
    return theano.tensor.cast(variable, theano.config.floatX)

def safe_update(dict_to, dict_from):
    """
    re-make update dictionary for safe updating
    """
    for key, val in dict(dict_from).iteritems():
        if key in dict_to:
            raise KeyError(key)
        dict_to[key] = val
    return dict_to

def get_idx_from_sent(sent, word_idx_map, k, filter_h, max_l=51):
    """
    Transforms sentence into a list of indices. Pad with zeroes.
    """
    x = []
    pad = filter_h - 1
    for i in xrange(pad):
        x.append(0)
    words = sent.split()
    for word in words:
        if word in word_idx_map:
            x.append(word_idx_map[word])
    while len(x) < max_l+2*pad:
        x.append(0)
    return x

def make_idx_data_cv(W, revs, word_idx_map, cv, k, filter_h, max_l=51):
    """
    Transforms sentences into a 2-d matrix.
    """
    train, test = [], []
    for rev in revs:
        sent = get_idx_from_sent(rev["text"], word_idx_map, k, filter_h, max_l)
        if max(sent) > 0:
            sent.append(rev["y"])
            if rev["split"]==cv:
                test.append(sent)
            else:
                train.append(sent)
    log_write("Number of urls to train: " + str(len(train)))
    log_write("Number of urls to test: " + str(len(test)))
    train = np.array(train,dtype="int")
    test = np.array(test,dtype="int")
    return [train, test]


if __name__=="__main__":
    log_write("loading data...")
    x = cPickle.load(open("mr.p","rb"))
    revs, W, word_idx_map= x[0], x[1], x[2]
    log_write("data loaded!")
    sample_row = W[word_idx_map[((revs[0]['text']).split())[0]]]
    k = len(sample_row)

    max_filter = 5
    filter_hs = [3,4,max_filter]
    feature_maps_per_filter = 50
    hidden_units = [feature_maps_per_filter,2]

    mode = "-static"
    word_vectors = "-word2vec"
    non_static=False
    execfile("conv_net_classes.py")
    U = W.astype(dtype="float32")
    results = []
    r = range(0,1) # r = range(0,10)
    for i in r:
        datasets = make_idx_data_cv(W, revs, word_idx_map, i, k, max_filter, max_l=56)
        perf = train_conv_net(datasets,
                              U,
                              k,
                              filter_hs,
                              hidden_units,
                              lr_decay=0.95,
                              conv_non_linear="relu",
                              shuffle_batch=True,
                              n_epochs=5,
                              sqr_norm_lim=9,
                              non_static=non_static,
                              batch_size=50,
                              dropout_rate=[0.5])
        log_write("cv: " + str(i) + ", perf: " + str(perf))
        results.append(perf)
    log_write(str(np.mean(results)))
