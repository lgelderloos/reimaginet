from funktional.util import grouper
from imaginet.multitask import *
import numpy
import imaginet.data_provider as dp
import imaginet.driver
from  sklearn.preprocessing import StandardScaler
from imaginet.simple_data import SimpleData, compressed
import sys
import os
import cPickle as pickle
import gzip
from evaluate import ranking
import random
from collections import Counter

def train(dataset='coco',
          datapath='.',
          model_path='.',
          tokenize=compressed,
          max_norm=None,
          min_df=10,
          scale=True,
          epochs=1,
          batch_size=64,
          shuffle=True,
          size_embed=128,
          size_hidden=512,
          depth=2,
          validate_period=64*1000,
          limit=None,
          seed=None):
    sys.setrecursionlimit(50000) # needed for pickling models
    if seed is not None:
        random.seed(seed)
        numpy.random.seed(seed)
    prov = dp.getDataProvider(dataset, root=datapath)
    data = SimpleData(prov, tokenize=tokenize, min_df=min_df, scale=scale, 
                      batch_size=batch_size, shuffle=shuffle, limit=limit)
    data.dump(model_path)
    encoder = Encoder(size_vocab=data.mapper.size(), size_embed=size_embed, size=size_hidden, depth=depth)
    imagine = Imagine(encoder, size=4096)
    trainer = TaskTrainer({'imagine': imagine}, max_norm=max_norm)
    do_training(trainer, 'imagine', data, epochs, validate_period, model_path)
    
def do_training(trainer, taskid, data, epochs, validate_period, model_path):
    task = trainer.tasks[taskid]
    def valid_loss():
        result = []
        for item in data.iter_valid_batches():
            inp, target_v, _, _ = item
            result.append(task.loss_test(inp, target_v))
        return result
    for epoch in range(1, epochs + 1):
            print len(task.params())
            costs = Counter()
            for _j, item in enumerate(data.iter_train_batches()):
                j = _j + 1
                inp, target_v, _, _ = item
                cost = task.train(inp, target_v)
                costs += Counter({'cost':cost, 'N':1})
                print epoch, j, j*data.batch_size, "train", "".join([str(costs['cost']/costs['N'])])
                if j*data.batch_size % validate_period == 0:
                        print epoch, j, 0, "valid", "".join([str(numpy.mean(valid_loss()))])
                sys.stdout.flush()
            pickle.dump(trainer, 
                        gzip.open(os.path.join(model_path, 'model.{0}.pkl.gz'.format(epoch)),'w'),
                        protocol=pickle.HIGHEST_PROTOCOL)
    pickle.dump(trainer, 
                    gzip.open(os.path.join(model_path, 'model.pkl.gz'), 'w'), 
                    protocol=pickle.HIGHEST_PROTOCOL)
    
def evaluate(dataset='coco',
             datapath='.',
             model_path='.',
             model_name='model.pkl.gz',
             batch_size=128
            ):
    M = load(model_path, model_name=model_name)
    scaler = M['scaler']
    task = M['model'].tasks['imagine']
    batcher = M['batcher']
    mapper = M['batcher'].mapper
    prov   = dp.getDataProvider(dataset, root=datapath)
    inputs = list(mapper.transform([compressed(sent) for sent in prov.iterSentences(split='val') ]))
    predictions = numpy.vstack([ task.predict(batcher.batch_inp(batch))
                          for batch in grouper(inputs, batch_size) ])

    sents  = list(prov.iterSentences(split='val'))
    images = list(prov.iterImages(split='val'))
    img_fs = list(scaler.transform([ image['feat'] for image in images ]))
    correct_img = numpy.array([ [ sents[i]['imgid']==images[j]['imgid']
                                  for j in range(len(images)) ]
                                for i in range(len(sents)) ] )
    return ranking(img_fs, predictions, correct_img, ns=(1,5,10), exclude_self=False)

def load(d, model_name='model.pkl.gz'):
    def load_pklgz(f):
        return pickle.load(gzip.open(os.path.join(d, f)))
    batcher, scaler, model = map(load_pklgz, ['batcher.pkl.gz','scaler.pkl.gz', model_name])
    mapper = batcher.mapper
    return {'batcher': batcher, 'scaler': scaler, 'model': model }
