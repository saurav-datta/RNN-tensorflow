from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

import time

import tensorflow as tf
import numpy as np


def matmul3d(X, W):
    """Wrapper for tf.matmul to handle a 3D input tensor X.
    Will perform multiplication along the last dimension.

    Args:
      X: [m,n,k]
      W: [k,l]

    Returns:
      XW: [m,n,l]
    """
    Xr = tf.reshape(X, [-1, tf.shape(X)[2]])
    XWr = tf.matmul(Xr, W)
    newshape = [tf.shape(X)[0], tf.shape(X)[1], tf.shape(W)[1]]
    return tf.reshape(XWr, newshape)


def MakeFancyRNNCell(H, keep_prob, num_layers=1):
    """Make a fancy RNN cell.

    Use tf.nn.rnn_cell functions to construct an LSTM cell.
    Initialize forget_bias=0.0 for better training.

    Args:
      H: hidden state size
      keep_prob: dropout keep prob (same for input and output)
      num_layers: number of cell layers

    Returns:
      (tf.nn.rnn_cell.RNNCell) multi-layer LSTM cell with dropout
    """
    cells = []
    for _ in range(num_layers):
      cell = tf.nn.rnn_cell.BasicLSTMCell(H, forget_bias=0.0)
      cell = tf.nn.rnn_cell.DropoutWrapper(
          cell, input_keep_prob=keep_prob, output_keep_prob=keep_prob)
      cells.append(cell)
    return tf.nn.rnn_cell.MultiRNNCell(cells)


# Decorator-foo to avoid indentation hell.
# Decorating a function as:
# @with_self_graph
# def foo(self, ...):
#     # do tensorflow stuff
#
# Makes it behave as if it were written:
# def foo(self, ...):
#     with self.graph.as_default():
#         # do tensorflow stuff
#
# We hope this will save you some indentation, and make things a bit less
# error-prone.
def with_self_graph(function):
    def wrapper(self, *args, **kwargs):
        with self.graph.as_default():
            return function(self, *args, **kwargs)
    return wrapper


class RNNLM(object):
    def __init__(self, graph=None, *args, **kwargs):
        """Init function.

        This function just stores hyperparameters. You'll do all the real graph
        construction in the Build*Graph() functions below.

        Args:
          V: vocabulary size
          H: hidden state dimension
          num_layers: number of RNN layers (see tf.nn.rnn_cell.MultiRNNCell)
        """
        # Set TensorFlow graph. All TF code will work on this graph.
        self.graph = graph or tf.Graph()
        self.SetParams(*args, **kwargs)

    @with_self_graph
    def SetParams(self, V, H, softmax_ns=200, num_layers=1):
        # Model structure; these need to be fixed for a given model.
        self.V = V
        self.H = H
        self.num_layers = num_layers

        # Training hyperparameters; these can be changed with feed_dict,
        # and you may want to do so during training.
        with tf.name_scope("Training_Parameters"):
            # Number of samples for sampled softmax.
            self.softmax_ns = softmax_ns

            self.learning_rate_ = tf.placeholder(tf.float32, [], name="learning_rate")

            # For gradient clipping, if you use it.
            # Due to a bug in TensorFlow, this needs to be an ordinary python
            # constant instead of a tf.constant.
            self.max_grad_norm_ = 1.0

            self.use_dropout_ = tf.placeholder_with_default(
                False, [], name="use_dropout")

            # If use_dropout is fed as 'True', this will have value 0.5.
            self.dropout_keep_prob_ = tf.cond(
                self.use_dropout_,
                lambda: tf.constant(0.5),
                lambda: tf.constant(1.0),
                name="dropout_keep_prob")

            # Dummy for use later.
            self.no_op_ = tf.no_op()


    @with_self_graph
    def BuildCoreGraph(self):
        """Construct the core RNNLM graph, needed for any use of the model.

        This should include:
        - Placeholders for input tensors (input_w_, initial_h_, target_y_)
        - Variables for model parameters
        - Tensors representing various intermediate states
        - A Tensor for the final state (final_h_)
        - A Tensor for the output logits (logits_), i.e. the un-normalized argument
          of the softmax(...) function in the output layer.
        - A scalar loss function (loss_)

        Your loss function should be a *scalar* value that represents the
        _average_ loss across all examples in the batch (i.e. use tf.reduce_mean,
        not tf.reduce_sum).

        You shouldn't include training or sampling functions here; you'll do
        this in BuildTrainGraph and BuildSampleGraph below.

        We give you some starter definitions for input_w_ and target_y_, as
        well as a few other tensors that might help. We've also added dummy
        values for initial_h_, logits_, and loss_ - you should re-define these
        in your code as the appropriate tensors.

        See the in-line comments for more detail.
        """
        # Input ids, with dynamic shape depending on input.
        # Should be shape [batch_size, max_time] and contain integer word indices.
        self.input_w_ = tf.placeholder(tf.int32, [None, None], name="w")

        # Initial hidden state. You'll need to overwrite this with cell.zero_state
        # once you construct your RNN cell.
        self.initial_h_ = None

        # Final hidden state. You'll need to overwrite this with the output from
        # tf.nn.dynamic_rnn so that you can pass it in to the next batch (if
        # applicable).
        self.final_h_ = None

        # Output logits, which can be used by loss functions or for prediction.
        # Overwrite this with an actual Tensor of shape
        # [batch_size, max_time, V].
        self.logits_ = None

        # Should be the same shape as inputs_w_
        self.target_y_ = tf.placeholder(tf.int32, [None, None], name="y")

        # Replace this with an actual loss function
        self.loss_ = None

        # Get dynamic shape info from inputs
        with tf.name_scope("batch_size"):
            self.batch_size_ = tf.shape(self.input_w_)[0]
        with tf.name_scope("max_time"):
            self.max_time_ = tf.shape(self.input_w_)[1]

        # Get sequence length from input_w_.
        # TL;DR: pass this to dynamic_rnn.
        # This will be a vector with elements ns[i] = len(input_w_[i])
        # You can override this in feed_dict if you want to have different-length
        # sequences in the same batch, although you shouldn't need to for this
        # assignment.
        self.ns_ = tf.tile([self.max_time_], [self.batch_size_, ], name="ns")

        #### YOUR CODE HERE ####
        # See hints in instructions!
        
        # Construct embedding layer
        init_scale=1
        with tf.name_scope("Embedding_Layer"):
            self.W_in_ = tf.get_variable(name="W_in", 
                                         shape=[self.V, self.H], 
                                         initializer=tf.random_uniform_initializer(minval=-init_scale, maxval=init_scale))
            self.x_ = tf.nn.embedding_lookup(self.W_in_, self.input_w_, name="x")

            
#sdatta
# Shape of W_in_ [10000, 200]
# Shape of x_ [None, None, 200]
# Shape of self.input_w_ [None, None]
# Value of self.V 10000
# Value of self.H 200
# Type of self.initial_h_ <class 'tuple'> ||  shape=(?, 200)
# Type of self.output_state_ <class 'tensorflow.python.framework.ops.Tensor'>, shape [None, None, 200]
# Type of self.final_h_ <class 'tuple'> || shape=(?, 200)
    
        # Construct RNN/LSTM cell and recurrent layer.
        #TODO, check for num_layers
        with tf.name_scope("Recurrent_Layer"):
            self.cell_ = MakeFancyRNNCell(self.H, self.dropout_keep_prob_, self.num_layers)
            
            #initial state
            self.initial_h_ = self.cell_.zero_state(batch_size=self.batch_size_, dtype=tf.float32)
            
            # Recurrent layer 
            self.output_state_, self.final_h_ = tf.nn.dynamic_rnn(cell=self.cell_, 
                                                                 inputs=self.x_, 
                                                                 initial_state=self.initial_h_, 
                                                                  dtype=tf.float32) 



        # Softmax output layer, over vocabulary. Just compute logits_ here.
        # Hint: the matmul3d function will be useful here; it's a drop-in
        # replacement for tf.matmul that will handle the "time" dimension
        # properly.
        with tf.name_scope("Softmax_Output_Layer"):
            
            self.W_out_ = tf.get_variable(name="W_out", 
                                          shape=[self.H, self.V], 
                                          initializer=tf.random_uniform_initializer(minval=-init_scale, maxval=init_scale))
            self.b_out_ = tf.get_variable("b_out", shape=[self.V,], initializer=tf.zeros_initializer())
            self.logits_ = tf.add(matmul3d(self.output_state_, self.W_out_), self.b_out_, name="logits")
        


        # Loss computation (true loss, for prediction)
        with tf.name_scope("True_Loss_Computation"):
            #TODO: Replace sparse_softmax_cross_entropy_with_logits with softmax_cross_entropy_with_logits_v2
            self.loss_ = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(labels=self.target_y_, logits=self.logits_))  

        #### END(YOUR CODE) ####


    @with_self_graph
    def BuildTrainGraph(self):
        """Construct the training ops.

        You should define:
        - train_loss_ : sampled softmax loss, for training
        - train_step_ : a training op that can be called once per batch

        Your loss function should be a *scalar* value that represents the
        _average_ loss across all examples in the batch (i.e. use tf.reduce_mean,
        not tf.reduce_sum).
        """
        # Replace this with an actual training op
        self.train_step_ = None

        # Replace this with an actual loss function
        self.train_loss_ = None

        #### YOUR CODE HERE ####
        # See hints in instructions!

        # Define approximate loss function.
        # Note: self.softmax_ns (i.e. k=200) is already defined; use that as the
        # number of samples.
            # Loss computation (sampled, for training)
        self.per_example_train_loss_ = tf.nn.sampled_softmax_loss(weights= tf.transpose(self.W_out_), 
                                                                  biases= self.b_out_, 
                                                                  labels= tf.expand_dims(tf.reshape(self.target_y_,[-1,]),1), 
                                                                  inputs= tf.reshape(self.output_state_,[-1,self.H]), 
                                                                  num_sampled=self.softmax_ns, 
                                                                  num_classes=self.V)
                                                                  
        
        self.train_loss_ = tf.reduce_mean(self.per_example_train_loss_, name = "train_loss")



        # Define optimizer and training op
        #Source: https://stackoverflow.com/questions/36498127/how-to-apply-gradient-clipping-in-tensorflow
        self.optimizer_ = tf.train.AdamOptimizer(learning_rate=self.learning_rate_)        
        self.gradients, self.variables = zip(*self.optimizer_.compute_gradients(self.train_loss_))
        self.gradients, _ = tf.clip_by_global_norm(self.gradients, 5.0)
        self.train_step_ = self.optimizer_.apply_gradients(zip(self.gradients, self.variables))
        #### END(YOUR CODE) ####

    @with_self_graph
    def BuildSamplerGraph(self):
        """Construct the sampling ops.

        You should define pred_samples_ to be a Tensor of integer indices for
        sampled predictions for each batch element, at each timestep.

        Hint: use tf.multinomial, along with a couple of calls to tf.reshape
        """
        # Replace with a Tensor of shape [batch_size, max_time, num_samples = 1]
        #self.pred_samples_ = None

        #### YOUR CODE HERE ####
        self.pred_samples_ = tf.reshape(
                tf.multinomial(
                    logits=tf.reshape(self.logits_,[-1,self.V]), 
                    num_samples=1),
                [self.batch_size_, self.max_time_, 1])

        #### END(YOUR CODE) ####

