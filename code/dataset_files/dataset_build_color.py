"""

Script to generate a dataset comprising decalibrated point clouds and images
For sequence: 2011_09_26

"""

import argparse
import glob
import matplotlib.pyplot as plt
from natsort import natsorted as ns
import numpy as np
import os
import re
import scipy.misc as smc
from skimage import io

plt.ion()


# Image properties

IMG_HT = 375
IMG_WDT = 1242

# Intrinsic calibration

fx = 7.215377e+02
fy = 7.215377e+02
cx = 6.095593e+02
cy = 1.728540e+02

K = np.array([7.215377e+02, 0.000000e+00, 6.095593e+02, \
	0.000000e+00, 7.215377e+02, 1.728540e+02, \
	0.000000e+00, 0.000000e+00, 1.000000e+00]).reshape(3,3)

# Extrinsic calibration

velo_to_cam_R = np.array([7.533745e-03, -9.999714e-01, -6.166020e-04, \
	1.480249e-02, 7.280733e-04, -9.998902e-01, \
	9.998621e-01, 7.523790e-03, 1.480755e-02]).reshape(3,3)
velo_to_cam_T = np.array([-4.069766e-03, -7.631618e-02, -2.717806e-01]).reshape(3,1)

velo_to_cam = np.vstack((np.hstack((velo_to_cam_R, velo_to_cam_T)), np.array([[0,0,0,1]])))

# Rectifying rotation (to make all images coplanar)
R_rect_00 =  np.array([9.999239e-01, 9.837760e-03, -7.445048e-03, 0.0,
					  -9.869795e-03, 9.999421e-01, -4.278459e-03, 0.0,
					   7.402527e-03, 4.351614e-03, 9.999631e-01,  0.0,
					   0.0,          0.0,          0.0,           1.0]).reshape(4,4)

# Move from cam_00 to cam_02
cam_02_transform = np.array([1.0, 0.0, 0.0, 4.485728e+01/fx,
							 0.0, 1.0, 0.0, 2.163791e-01/fy,
							 0.0, 0.0, 1.0, 2.745884e-03,
							 0.0, 0.0, 0.0, 1.0]).reshape(4,4)


# Command-line argument parser
parser = argparse.ArgumentParser(description = 'Create dataset to train CalibNet')
parser.add_argument('-path', help = 'path to KITTI raw data folder', type = str)
parser.add_argument('-randomseed', help = 'Seed for RNG', type = int, default = 12345)
args = parser.parse_args()

# Path to KITTI raw sequence dir (eg. KITTI_base_dir/2011_09_26/2011_09_26_drive_xxxx)
main_path = args.path

# Seed the RNG
np.random.seed(args.randomseed)


# Create directories to store data (if they don't already exist)
if not os.path.exists(main_path + '_sync/depth_maps'):
	os.makedirs(main_path + '_sync/depth_maps')

if not os.path.exists(main_path + '_sync/target_imgs'):
	os.makedirs(main_path + '_sync/target_imgs')

if not os.path.exists(main_path + '_sync/depth_maps_transformed'):
	os.makedirs(main_path + '_sync/depth_maps_transformed')


# Path definitions
depth_maps_folder = main_path + '_sync/depth_maps'
target_img_folder = main_path + '_sync/target_imgs'
depth_maps_transformed_folder = main_path + '_sync/depth_maps_transformed'

imgs_files = ns(glob.glob(main_path + '_sync/image_02/data/*.png'))
cloud_files = ns(glob.glob(main_path + '_sync/velodyne_points/data/*.bin'))
print(len(imgs_files), len(cloud_files))

# Perturbation range (rotation and translation)
angle_limit = 0.34722965035593395/1.25
tr_limit = 0.34722965035593395/1.25

angle_list = np.zeros((1,16), dtype = np.float32)

# For each image-velodyne scan pair
for img_name, cloud_name in zip(imgs_files, cloud_files):

	print(img_name[-14:-4], cloud_name[-14:-4])
	if img_name[-14:-4] != cloud_name[-14:-4]:
		continue

	# Generate a random decalibration (rotation, translation)
	omega_x = angle_limit*np.random.random_sample() - (angle_limit/2.0)
	omega_y = angle_limit*np.random.random_sample() - (angle_limit/2.0)
	omega_z = angle_limit*np.random.random_sample() - (angle_limit/2.0)
	tr_x = tr_limit*np.random.random_sample() - (tr_limit/2.0)
	tr_y = tr_limit*np.random.random_sample() - (tr_limit/2.0)
	tr_z = tr_limit*np.random.random_sample() - (tr_limit/2.0)

	# Generate rotation matrix from the decalibration (Rodriguez formula/ SO(3) Exp map)
	theta = np.sqrt(omega_x**2 + omega_y**2 + omega_z**2)
	omega_cross = np.array([0.0, -omega_z, omega_y, \
		omega_z, 0.0, -omega_x, \
		-omega_y, omega_x, 0.0]).reshape(3,3)
	R = np.eye(3,3) + ((np.sin(theta) / theta) * omega_cross) + \
	(((1.0 - np.cos(theta)) / (theta**2)) * np.matmul(omega_cross, omega_cross))
	# Generate translation vector from the decalibration
	T = np.array([tr_x, tr_y, tr_z]).reshape(3,1)

	# Stack the rotation and translation to form a homogeneous transform matrix (4 x 4)
	random_transform = np.vstack((np.hstack((R, T)), np.array([[0.0, 0.0, 0.0, 1.0]])))

	# Ground-truth transform
	to_write_tr = np.expand_dims(np.ndarray.flatten(random_transform), 0)
	angle_list = np.vstack((angle_list, to_write_tr))


	points = np.fromfile(cloud_name, dtype=np.float32).reshape(-1,4)
	points = points[:,:3]
	ones_col = np.ones(shape=(points.shape[0],1))
	points = np.hstack((points,ones_col))
	current_img = smc.imread(img_name)

	img = smc.imread(img_name)
	img_ht = img.shape[0]
	img_wdt = img.shape[1]

	points_in_cam_axis = np.matmul(R_rect_00, (np.matmul(velo_to_cam, points.T)))
	transformed_points = np.matmul(random_transform, points_in_cam_axis)

	points_2d = np.matmul(K, np.matmul(cam_02_transform, transformed_points)[:-1,:])

	Z = points_2d[2,:]
	x = (points_2d[0,:]/Z).T
	y = (points_2d[1,:]/Z).T

	x = np.clip(x, 0.0, img_wdt - 1)
	y = np.clip(y, 0.0, img_ht - 1)

	reprojected_img = np.zeros_like(img)
	for x_idx, y_idx,z_idx in zip(x,y,Z):
		if(z_idx>0):
			reprojected_img[int(y_idx), int(x_idx)] = z_idx

	smc.imsave(depth_maps_transformed_folder + "/" + img_name[-14:], reprojected_img)

	points_2d = np.matmul(K, np.matmul(cam_02_transform, points_in_cam_axis)[:-1,:])

	Z = points_2d[2,:]
	x = (points_2d[0,:]/Z).T
	y = (points_2d[1,:]/Z).T

	x = np.clip(x, 0.0, img_wdt - 1)
	y = np.clip(y, 0.0, img_ht - 1)

	reprojected_img = np.zeros_like(img)
	for x_idx, y_idx,z_idx in zip(x,y,Z):
		if(z_idx>0):
			reprojected_img[int(y_idx), int(x_idx)] = z_idx
	pooled_img = reprojected_img

	print(img_name[-14:])

	reconstructed_img = current_img*(pooled_img>0.)
	smc.imsave(depth_maps_folder + '/' + img_name[-14:], pooled_img)
	smc.imsave(target_img_folder + '/' + img_name[-14:], reconstructed_img)

np.savetxt(depth_maps_transformed_folder + '/../angle_list.txt', angle_list[1:], fmt = "%.4f")
