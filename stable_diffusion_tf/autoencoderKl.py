import tensorflow as tf
from tensorflow import keras
import tensorflow_addons as tfa

from .layers import apply_seq

class PaddedConv2D(keras.layers.Layer):
    def __init__(
        self,
        channels,
        kernel_size,
        padding = 0,
        stride = 1,
        name = None
    ):
        super().__init__()
        self.padding2d = keras.layers.ZeroPadding2D((padding, padding), name = name)
        self.conv2d = keras.layers.Conv2D(
            channels, kernel_size = kernel_size, strides = (stride, stride), name = name
        )

    def call(self, x):
        x = self.padding2d(x)
        return self.conv2d(x)

class AttentionBlock(keras.layers.Layer):
    def __init__(self, channels):
        super().__init__()
        self.norm = tfa.layers.GroupNormalization(epsilon=1e-5, name = "Normalization")
        self.q = PaddedConv2D(channels, 1, name = "Query")
        self.k = PaddedConv2D(channels, 1, name = "key")
        self.v = PaddedConv2D(channels, 1, name = "Value")
        self.proj_out = PaddedConv2D(channels, 1, name = "ProjectedOut")

    def call(self, x):
        h_ = self.norm(x)
        q, k, v = self.q(h_), self.k(h_), self.v(h_)

        # Compute attention
        b, h, w, c = q.shape
        q = tf.reshape(q, (-1, h * w, c))  # b,hw,c
        k = keras.layers.Permute((3, 1, 2))(k)
        k = tf.reshape(k, (-1, c, h * w))  # b,c,hw
        w_ = q @ k
        w_ = w_ * (c ** (-0.5))
        w_ = keras.activations.softmax(w_)

        # Attend to values
        v = keras.layers.Permute((3, 1, 2))(v)
        v = tf.reshape(v, (-1, c, h * w))
        w_ = keras.layers.Permute((2, 1))(w_)
        h_ = v @ w_
        h_ = keras.layers.Permute((2, 1))(h_)
        h_ = tf.reshape(h_, (-1, h, w, c))
        return x + self.proj_out(h_)


class ResnetBlock(keras.layers.Layer):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.norm1 = tfa.layers.GroupNormalization(epsilon = 1e-5, name = "Normalization01")
        self.conv1 = PaddedConv2D(out_channels, 3, padding = 1, name = "Convolutional01")
        self.norm2 = tfa.layers.GroupNormalization(epsilon = 1e-5, name = "Normalization01")
        self.conv2 = PaddedConv2D(out_channels, 3, padding = 1, name = "Convolutional02")
        self.nin_shortcut = (
            PaddedConv2D(out_channels, 1, name = "NinShortcut")
            if in_channels != out_channels
            else lambda x: x
        )

    def call(self, x):
        h = self.conv1(keras.activations.swish(self.norm1(x)))
        h = self.conv2(keras.activations.swish(self.norm2(h)))
        return self.nin_shortcut(x) + h


class Decoder(keras.Sequential):
    def __init__(self):
        super().__init__(
            [
                keras.layers.Lambda(lambda x: 1 / 0.18215 * x),
                PaddedConv2D(4, 1, name = "PostQuantConvolutionalIn"), # Z to block in
                PaddedConv2D(512, 3, padding = 1, name = "ConvolutionalIn"),
                ResnetBlock(512, 512),
                AttentionBlock(512),
                ResnetBlock(512, 512),
                ResnetBlock(512, 512),
                ResnetBlock(512, 512),
                ResnetBlock(512, 512),
                keras.layers.UpSampling2D(size = (2, 2)),
                PaddedConv2D(512, 3, padding = 1),
                ResnetBlock(512, 512),
                ResnetBlock(512, 512),
                ResnetBlock(512, 512),
                keras.layers.UpSampling2D(size = (2, 2)),
                PaddedConv2D(512, 3, padding = 1),
                ResnetBlock(512, 256),
                ResnetBlock(256, 256),
                ResnetBlock(256, 256),
                keras.layers.UpSampling2D(size = (2, 2)),
                PaddedConv2D(256, 3, padding = 1),
                ResnetBlock(256, 128),
                ResnetBlock(128, 128),
                ResnetBlock(128, 128),
                tfa.layers.GroupNormalization(epsilon = 1e-5, name = "NormalizationOut"),
                keras.layers.Activation("swish"),
                PaddedConv2D(3, 3, padding = 1, name = "ConvolutionalOut"),
            ]
        )


class Encoder(keras.Sequential):
    def __init__(self):
        super().__init__(
            [
                # Downsample
                PaddedConv2D(128, 3, padding = 1 , name = "EncoderDownsample"),
                ResnetBlock(128,128),
                ResnetBlock(128, 128),
                PaddedConv2D(128 , 3 ,  padding = 1, stride = 2),
                
                ResnetBlock(128,256),
                ResnetBlock(256, 256),
                PaddedConv2D(256 , 3 ,  padding = 1, stride = 2),
                
                ResnetBlock(256,512),
                ResnetBlock(512, 512),
                PaddedConv2D(512 , 3 ,  padding = 1, stride = 2),
                
                ResnetBlock(512,512),
                ResnetBlock(512, 512),
                
                ResnetBlock(512, 512),
                AttentionBlock(512),
                ResnetBlock(512, 512),
                
                tfa.layers.GroupNormalization(epsilon = 1e-5) , 
                keras.layers.Activation("swish"),
                PaddedConv2D(8, 3, padding = 1 ),
                PaddedConv2D(8, 1 ),
                keras.layers.Lambda(lambda x : x[... , :4] * 0.18215)
            ]
        )
