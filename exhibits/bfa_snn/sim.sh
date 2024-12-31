#!/bin/sh
################################################################################
# Simulate the BFA-SNN on the MNIST database
################################################################################
DATA_DIR="/content/ngc-museum/data/"

rm -r /content/ngc-museum/exhibits/bfa_snn/exp/* ## clear out experimental directory
python3 /content/ngc-museum/exhibits/bfa_snn/train_bfasnn.py  --dataX="$DATA_DIR/trainX.npy" \
                        --dataY="$DATA_DIR/trainY.npy" \
                        --devX="$DATA_DIR/validX.npy" \
                        --devY="$DATA_DIR/validY.npy" \
                        --verbosity=1
