import tensorflow as tf 
import model as M
import layers as L
import utils2

class MaskRCNN():
	def __init__(self,config):
		self.config = config
		self.build_graph(config)

	def build_graph(self,config):
		h,w = config.IMAGE_SHAPE[:2]
		if h / 2**6 != int(h / 2**6) or w / 2**6 != int(w / 2**6):
			raise Exception("Image size must be dividable by 2 at least 6 times to avoid fractions when downscaling and upscaling. For example, use 256, 320, 384, 448, 512, ... etc. ")

		print(config.IMAGE_SHAPE.tolist())
		image_holder = tf.placeholder(tf.float32,[None]+config.IMAGE_SHAPE.tolist())
		meta_holder = tf.placeholder(tf.float32,[None])

		C1,C2,C3,C4,C5 = resnet(image_holder,stage5=True)
		P5 = L.conv2D(C5,1,256,'P5')
		P4 = L.upSampling(P5,2,'U5') + L.conv2D(C4,1,256,'P4')
		P3 = L.upSampling(P4,2,'U4') + L.conv2D(C3,1,256,'P3')
		P2 = L.upSampling(P3,2,'U3') + L.conv2D(C2,1,256,'P2')
		P2 = L.conv2D(P2,3,256,'P2_')
		P3 = L.conv2D(P3,3,256,'P3_')
		P4 = L.conv2D(P4,3,256,'P4_')
		P5 = L.conv2D(P5,3,256,'P5_')
		P6 = L.maxpooling(P5,1,2,'P6_')
		rpn_fm = [P2,P3,P4,P5,P6]
		mrcnn_fm = [P2,P3,P4,P5]

		self.anchors = utils2.generate_pyramid_anchors(config.RPN_ANCHOR_SCALES,config.RPN_ANCHOR_RATIOS,config.BACKBONE_SHAPES,config.BACKBONE_STRIDES,config.RPN_ANCHOR_STRIDE)

		rpn = rpn(config.RPN_ANCHOR_STRIDE,len(config.RPN_ANCHOR_RATIOS), 256)

		scale_rpns = []
		for p_layer in rpn_fm:
			scale_rpns.append(rpn.pred(p_layer))

		scale_rpns = list(zip(*scale_rpns))
		scale_rpns = [tf.concat(a,1) for a in scale_rpns]
		rpn_logits, rpn_class, rpn_bbox = scale_rpns
		# TODO: add proposal layer, detection layer and mask layers

block_num = 0
def res_block(mod,kernel_size,channels,stride,with_short):
	chn1, chn2, chn3 = channels
	with tf.variable_scope('block_'+str(block_num)):
		inputLayer = mod.get_current()
		mod.convLayer(1,chn1,stride=stride,batch_norm=True,activation=M.PARAM_RELU)
		mod.convLayer(kernel_size,chn2,batch_norm=True,activation=M.PARAM_RELU)
		branch = mod.convLayer(1,chn3,batch_norm=True)
		# Shortcut
		mod.set_current(inputLayer)
		if with_short:
			mod.convLayer(1,chn3,stride=stride,batch_norm=True)
		mod.sum(branch)
		mod.activation(M.PARAM_RELU)
	block_num += 1

def resnet(inputLayer,stage5=False):
	with tf.variable_scope('resnet'):
		mod = M.Model(inputLayer,inputLayer.get_shape().as_list())
		# 1
		mod.padding(3)
		mod.convLayer(7,64,stride=2,pad='VALID',batch_norm=True,activation=M.PARAM_RELU)
		mod.maxpoolLayer(3,stride=2)
		C1 = mod.get_current_layer()
		# 2
		res_block(mod,3,[64,64,256],1,True)
		res_block(mod,3,[64,64,256],1,False)
		res_block(mod,3,[64,64,256],1,False)
		C2 = mod.get_current_layer()
		# 3
		res_block(mod,3,[128,128,512],2,True)
		res_block(mod,3,[128,128,512],1,False)
		res_block(mod,3,[128,128,512],1,False)
		res_block(mod,3,[128,128,512],1,False)
		C3 = mod.get_current_layer()
		# 4
		res_block(mod,3,[256,256,1024],2,True)
		for i in range(22):
			res_block(mod,3,[256,256,1024],1,False)
		C4 = mod.get_current_layer()
		# 5
		if stage5:
			mod.res_block(mod,3,[512,512,2048],2,True)
			mod.res_block(mod,3,[512,512,2048],1,False)
			mod.res_block(mod,3,[512,512,2048],1,False)
			C5 = mod.get_current_layer()
		else:
			C5 = None
	return mod,C1,C2,C3,C4,C5

class rpn():
	def __init__(self,anchor_stride,anchor_density,channels):
		self.anchor_stride = anchor_stride
		self.anchor_density = anchor_density
		self.channels = channels
		self.reuse=False

	def pred(self,inp):
		with tf.variable_scope('RPN',reuse=self.reuse):
			# input_holder = tf.placeholder(tf.float32,[None,None,None,channels])
			shared_feature = L.convLayer(inp,3,512,stride=self.anchor_stride,'rpn_shared')
			# logits
			rpn_logits = L.convLayer(shared_feature,1,2*self.anchor_density,'rpn_logits')
			rpn_logits = tf.reshape(rpn_logits,[rpn_logits.get_shape().as_list()[0],-1,2])
			rpn_prob = tf.nn.softmax(rpn_logits)
			# bbox
			rpn_bbox = L.convLayer(shared_feature,1,4*self.anchor_density,'rpn_bbox')
			rpn_bbox = tf.reshape(rpn_bbox,[rpn_bbox.get_shape().as_list()[0],-1,4])
			self.reuse=True
		return rpn_logits,rpn_prob,rpn_bbox