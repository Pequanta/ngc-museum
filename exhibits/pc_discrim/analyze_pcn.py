from jax import numpy as jnp, random, nn, jit
import numpy as np
import sys, getopt as gopt, optparse
## bring in model from museum
#from ngcsimlib.controller import Controller
from pcn_model import load_model
## bring in ngc-learn analysis tools
from ngclearn.utils.model_utils import measure_ACC, measure_CatNLL
from ngclearn.utils.viz.dim_reduce import extract_tsne_latents, plot_latents

def eval_model(model, Xdev, Ydev, mb_size): ## evals model's test-time inference performance
    n_batches = int(Xdev.shape[0]/mb_size)

    latents = []
    n_samp_seen = 0
    nll = 0. ## negative Categorical log liklihood
    acc = 0. ## accuracy
    for j in range(n_batches):
        ## extract data block/batch
        idx = j * mb_size
        Xb = Xdev[idx: idx + mb_size,:]
        Yb = Ydev[idx: idx + mb_size,:]
        ## run model inference
        yMu_0, yMu, _ = model.process(obs=Xb, lab=Yb, adapt_synapses=False)
        latents.append(model.get_latents())
        ## record metric measurements
        _nll = measure_CatNLL(yMu_0, Yb) * Xb.shape[0] ## un-normalize score
        _acc = measure_ACC(yMu_0, Yb) * Yb.shape[0] ## un-normalize score
        nll += _nll
        acc += _acc

        n_samp_seen += Yb.shape[0]

    nll = nll/(Xdev.shape[0]) ## calc full dev-set nll
    acc = acc/(Xdev.shape[0]) ## calc full dev-set acc
    latents = jnp.concatenate(latents, axis=0)
    return nll, acc, latents

# read in general program arguments
options, remainder = gopt.getopt(sys.argv[1:], '',
                                 ["dataX=", "dataY=", "devX=", "devY="]
                                 )

dataX = "../data/mnist/testX.npy"
dataY = "../data/mnist/testY.npy"
for opt, arg in options:
    if opt in ("--dataX"):
        dataX = arg.strip()
    elif opt in ("--dataY"):
        dataY = arg.strip()
print("=> Data X: {} | Y: {}".format(dataX, dataY))

_X = jnp.load(dataX)
_Y = jnp.load(dataY)

#model = Controller()
#model.load_from_dir(directory="exp/pcn")
model = load_model("exp/pcn", dt=1., T=20) # PCN(model_dir="exp/pcn", exp_dir="exp", dt=1., T=10)

nll, acc, latents = eval_model(model, _X, _Y, mb_size=1000)
print("=> NLL = {}  Acc = {}".format(nll, acc))

print("Lat.shape = ",latents.shape)
codes = extract_tsne_latents(np.asarray(latents))
print("code.shape = ",codes.shape)
plot_latents(codes, _Y, plot_fname="pcn_latents.jpg")

## TODO: put in tSNE viz code to show what latents look like
