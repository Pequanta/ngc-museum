#from ngcsimlib.controller import Controller
from jax import numpy as jnp, random, nn, jit
import sys
from pc_model import PCN
from ngclearn.utils.model_utils import measure_ACC, measure_CatNLL

_X = jnp.load("../data/baby_mnist/babyX.npy")
_Y = jnp.load("../data/baby_mnist/babyY.npy")
# _X = jnp.load("/home/ago/Research/spiking-pff-learning/data/mnist/trainX.npy")
# _Y = jnp.load("/home/ago/Research/spiking-pff-learning/data/mnist/trainY.npy")
x_dim = _X.shape[1]
y_dim = _Y.shape[1]

n_iter = 20 #100
mb_size = 10 #200 # 256
# std of init - 0.025
n_batches = int(_X.shape[0]/mb_size)

dkey = random.PRNGKey(1234)
dkey, *subkeys = random.split(dkey, 10)

## build model
model = PCN(subkeys[1], x_dim, y_dim, hid1_dim=128, hid2_dim=128, T=10, # T=20 #hid=500
            dt=1., tau_m=10., act_fx="sigmoid", exp_dir="exp", model_name="pcn")

def eval_model(model, Xtest, Ytest, mb_size):
    n_batches = int(Xtest.shape[0]/mb_size)

    n_samp_seen = 0
    nll = 0. ## negative Categorical log liklihood
    acc = 0. ## accuracy
    for j in range(n_batches):
        dkey, *subkeys = random.split(dkey, 2)
        ## extract data block/batch
        idx = j * mb_size
        Xb = Xtest[idx: idx + mb_size,:]
        Yb = Ytest[idx: idx + mb_size,:]
        ## run model inference
        yMu_0, yMu = model.process(obs=Xb, lab=Yb, adapt_synapses=False)
        ## record metric measurements
        _nll = measure_CatNLL(yMu_0, _Y) * Xb.shape[0] ## un-normalize score
        _acc = measure_ACC(yMu_0, _Y) * Yb.shape[0] ## un-normalize score
        nll += _nll
        acc += _acc

        n_samp_seen += Yb.shape[0]
        print("\r {} processed ".format(nll/(n_samp_seen *1.), acc/(n_samp_seen *1.),
                                        n_samp_seen), end="")
    print()
    nll = nll/(Xtest.shape[0]) ## calc full dev-set nll
    acc = acc/(Xtest.shape[0]) ## calc full dev-set acc
    return nll, acc

nll, acc = eval_model(model, _X, _Y, mb_size)
print("-1: Acc = {}  NLL = {}".format(acc, nll))
for i in range(n_iter):
    ## shuffle data (to ensure i.i.d. assumption holds)
    dkey, *subkeys = random.split(dkey, 2)
    ptrs = random.permutation(subkeys[0],_X.shape[0])
    X = _X[ptrs,:]
    Y = _Y[ptrs,:]

    ## begin a single epoch
    n_samp_seen = 0
    for j in range(n_batches):
        dkey, *subkeys = random.split(dkey, 2)
        ## sample mini-batch of patterns
        idx = j * mb_size #j % 2 # 1
        Xb = X[idx: idx + mb_size,:]
        Yb = Y[idx: idx + mb_size,:]
        ## perform a step of inference/learning
        yMu_0, yMu = model.process(obs=Xb, lab=Yb, adapt_synapses=True)
        n_samp_seen += Yb.shape[0]
        print("\r {} processed ".format(n_samp_seen), end="")
    print()

    ## evaluate current progress of model on dev-set
    nll, acc = eval_model(model, _X, _Y, mb_size)
    print("{}: Acc = {}  NLL = {}".format(i, acc, nll))
