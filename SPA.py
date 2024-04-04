# -*- coding: utf-8 -*-
"""
Created on Fri Sep 29 09:08:25 2023

@author: Peter Tønning, Kevin Bach Gravesen, Magnus Linnet Madsen, Frederik P
"""

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from scipy.optimize import curve_fit, least_squares
from scipy.signal import find_peaks, savgol_filter, convolve, convolve2d
from scipy.fft import ifft2, fftshift, fft2, ifftshift
from math import isclose
import skimage.graph
from skimage.io import imread, imshow
from skimage.morphology import disk, rectangle
from skimage.color import rgb2gray
from skimage.transform import rotate
from skimage.filters import rank, gaussian
from skimage import util
from functions import *
import scipy.ndimage as ndi
import warnings



class SPA:
    def __init__(self, show_plots, chiplength, manual=False):
        self.show_plots = show_plots
        self.chiplength = chiplength  # 7229 um measured on the GDS, 2445 is the pixel width of the sensor (Both numbers inherent of the sensor and lens)
        self.manual = manual  # When true remember to call manual_input_output and set_um_per_pixel before analyze_image

    def set_um_per_pixel(self, point1, point2):
        warnings.filterwarnings('ignore')
        # For straight waveguides: calculating Euclidean distance between input and output.
        points = [np.array(point1), np.array(point2)]
        dist_pixels = np.linalg.norm(points[0] - points[1])

        self.mum_per_pixel = self.chiplength / dist_pixels

    def get_intensity_array(self, image_array):
        #Convert array values to 8-bit compatible values.
        warnings.filterwarnings('ignore')
        return np.clip(
            np.sqrt(image_array[:, :, 0] ** 2 + image_array[:, :, 1] ** 2 + image_array[:, :, 2] ** 2) / np.sqrt(
                3 * 255 ** 2) * 255, 0, 255)

    def insertion_detection(self, image, show_plots=True):
        warnings.filterwarnings('ignore')
        # Convert the image to a NumPy array
        image_array = np.array(image)
        image_array_shape = np.shape(image_array)

        scale_factor = 2 ** 3
        new_height = int(np.rint(image_array_shape[0] / scale_factor))  # New width in pixels
        new_width = int(np.rint(image_array_shape[1] / scale_factor))  # New height in pixels

        # Resize the image to the new dimensions
        resized_image = image.resize((new_width, new_height), Image.LANCZOS)
        resized_image_array = np.array(resized_image)

        # Define a simple convolution kernel
        kernel_size = 4
        kernel = np.ones([kernel_size, kernel_size]) / kernel_size ** 2

        # Apply convolution separately for each color channel
        filtered_channels = []
        for channel in range(3):  # RGB channels
            filtered_channel = convolve2d(resized_image_array[:, :, channel], kernel, mode='same', boundary='wrap')
            filtered_channels.append(filtered_channel)

        # Combine the filtered channels back into an RGB image
        filtered_image_array = np.stack(filtered_channels, axis=2)

        intensity_filtered_image_array = self.get_intensity_array(filtered_image_array)

        resized_input_index = np.unravel_index(np.argmax(intensity_filtered_image_array, axis=None),
                                               intensity_filtered_image_array.shape)

        input_height_index = int(resized_input_index[0] * scale_factor)
        input_width_index = int(resized_input_index[1] * scale_factor)

        height_tolerance_output = 100
        left_index_limit = int(new_width) - 20
        right_index_limit = int(new_width) - 1
        lower_index_limit = int((input_height_index - height_tolerance_output) / scale_factor)
        upper_index_limit = int((input_height_index + height_tolerance_output) / scale_factor)

        output_array = intensity_filtered_image_array[lower_index_limit: upper_index_limit,
                       left_index_limit: right_index_limit]
        resized_output_index = np.unravel_index(np.argmax(output_array, axis=None), output_array.shape)

        output_height_index = int((resized_output_index[0] + lower_index_limit) * scale_factor)
        output_width_index = int((resized_output_index[1] + left_index_limit) * scale_factor)
        return input_width_index, input_height_index, output_width_index, output_height_index

    def find_waveguide_angle(self, image_array, left_index_guess, left_right_separation, number_of_points):
        #Find the angle of the waveguide to ensure it is horizontal and rotate the image.
        warnings.filterwarnings('ignore')
        kernel = np.ones([1, 50]) / (1 * 50)
        smoothed_image_array = convolve2d(image_array, kernel)
        x_index_array = []
        max_height_index_array = []
        for index in range(0, number_of_points):
            x_index = left_index_guess + index * left_right_separation
            x_index_array.append(x_index)
            max_array = np.flip(np.mean(smoothed_image_array[:, x_index: left_index_guess + x_index + 1], axis=1))
            max_height_index = np.argmax(max_array - np.mean(max_array))
            max_height_index_array.append(max_height_index)

        param, covparam = curve_fit(self.linear_function, x_index_array, max_height_index_array)
        angle = np.degrees(np.arctan(param[0]))

        return angle, param, x_index_array, max_height_index_array

    def rotate_image(self, image, input_side="left"):
        warnings.filterwarnings('ignore')
        # Function to rotate images using left/right/flip commands. The script is written with input on the left.
        if input_side == "left":
            image = image.rotate(90, expand=True)

        elif input_side == "right":
            image = image.rotate(-90, expand=True)

        elif input_side == "flip":
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        else:
            raise Exception("Specify input side 'left', 'right', 'flip'")

        return image

    def optimize_parameter(self,parameter,image,left_indent,right_indent,waveguide_sum_width,IQR_neighbor_removal):
        #Optimizing the parameters used in the straight waveguide fit
        warnings.filterwarnings('ignore')
        plot_state = self.show_plots
        if plot_state:
            self.show_plots = False
        converge_alpha = []

        #Fitting for varying parameters
        if parameter == "left indent":
            indents = np.arange(201, 501, 2)
            for i in range(len(indents)):
                alpha_dB, r_squared, fit_x, fit_y, alpha_dB_variance = self.analyze_image(image, indents[i], right_indent,waveguide_sum_width, IQR_neighbor_removal)
                converge_alpha.append(alpha_dB)

        elif parameter == "right indent":
            indents = np.arange(150, 450, 2)
            for i in range(len(indents)):
                alpha_dB, r_squared, fit_x, fit_y, alpha_dB_variance = self.analyze_image(image, left_indent,indents[i],waveguide_sum_width,IQR_neighbor_removal)
                converge_alpha.append(alpha_dB)

        elif parameter == "sum width":
            indents = np.arange(40, 200, 1)
            for i in range(len(indents)):
                alpha_dB, r_squared, fit_x, fit_y, alpha_dB_variance = self.analyze_image(image, left_indent,right_indent, indents[i],IQR_neighbor_removal)
                converge_alpha.append(alpha_dB)

        else:
            raise Exception("Specify parameter 'left indent', 'right indent' or 'sum width'")

        #differentiate and smooth the determined alpha values
        dI = indents[1] - indents[0]
        smoothed_alpha = savgol_filter(converge_alpha, 4, 1, mode="nearest")
        alpha_indent = np.gradient(smoothed_alpha, dI)

        #Findng points below threshold
        index_min = []
        abs_tol = 0.01
        while abs_tol < 0.9:
            if len(index_min) == 0:
                zero_gradient_minus = []
                zero_gradient_plus = []
                for i in range(len(indents) - 1):
                    zero_gradient_p = isclose(alpha_indent[i], alpha_indent[i + 1], abs_tol=abs_tol)
                    zero_gradient_m = isclose(alpha_indent[i], alpha_indent[i - 1], abs_tol=abs_tol)
                    zero_gradient_minus.append(zero_gradient_m)
                    zero_gradient_plus.append(zero_gradient_p)
                    if zero_gradient_plus[i] == True and zero_gradient_minus[i] == True:
                        index_min.append(i)
            abs_tol = abs_tol + 0.01

        #Finding points where the variation in the surrounding points are ~0.
        num_neighbors = 5
        point_mean = []
        for index in index_min:
            neighbor_indexes = np.arange(index - num_neighbors, index + num_neighbors + 1, 1)
            neighbor_indexes = [x for x in neighbor_indexes if x > 0 and x < len(alpha_indent)]
            point_m = np.mean(smoothed_alpha[neighbor_indexes])
            point_diff = abs(point_m - smoothed_alpha[index])
            point_mean.append(point_diff)
        min_point_mean = point_mean.index(min(point_mean))
        ideal_indent = indents[index_min[min_point_mean]]

        self.show_plots = plot_state
        if self.show_plots:
            plt.figure(figsize=(10, 6))
            plt.plot(indents, alpha_indent)
            plt.axvline(ideal_indent, color='r', linestyle="dashed", label="minimum_index")
            plt.xlabel(parameter)
            plt.ylabel("$d\\alpha$/d(indent)")
            plt.legend(["$\\alpha$ values", "Smoothed alpha values", "Optimal indent: " + str(ideal_indent)])
            plt.title(parameter + " convergence with optimal indent: " + str(ideal_indent))
            plt.show()

        return ideal_indent

    def remove_outliers_IQR(self, x, data, blocks, num_neighbors):
        warnings.filterwarnings('ignore')
        # Removal of outliers using the interquartile method.
        data_blocks = np.array_split(data, blocks)
        x_blocks = np.array_split(x, blocks)
        x_blocks_indexes = [x[-1] for x in x_blocks]

        for i in range(len(data_blocks)):
            Q1 = np.percentile(data_blocks[i], 25, interpolation='midpoint')
            Q3 = np.percentile(data_blocks[i], 75, interpolation='midpoint')
            IQR = Q3 - Q1

            upper = Q3 + 1.5 * IQR
            lower = Q1 - 1.5 * IQR

            upper_array = np.where(data_blocks[i] >= upper)[0]
            lower_array = np.where(data_blocks[i] <= lower)[0]

            remove_array = np.concatenate((upper_array, lower_array))
            new_remove_array = []

            for index in remove_array:  # Finding indexes of neighbors to detected outliers
                neighbor_indexes = np.arange(index - num_neighbors, index + num_neighbors + 1, 1)
                neighbor_indexes = [x for x in neighbor_indexes if x > 0 and x < len(data_blocks[i])]
                new_remove_array += neighbor_indexes

            new_remove_array = list(set(new_remove_array))
            data_blocks[i] = np.delete(data_blocks[i], new_remove_array)  # removing outliers and neighbors from data
            x_blocks[i] = np.delete(x_blocks[i], new_remove_array)

        return np.concatenate(x_blocks), np.concatenate(data_blocks), x_blocks_indexes

    def linear_function(self, x, a, b):
        warnings.filterwarnings('ignore')
        return a * x + b

    def exponential_function_offset(self, x, a, b, c):
        warnings.filterwarnings('ignore')
        return a * np.exp(-b * x) + c

    def manual_input_and_output(self, input_point, output_point):
        # For spiral waveguides the input/output needs to be manually input.
        self.input_width_index = input_point[0]
        self.input_height_index = input_point[1]

        self.output_width_index = output_point[0]
        self.output_height_index = output_point[1]

    def calculate_confidence_interval(self, fit_parameters, fit_parameters_cov_var_matrix, x, confidence_interval):
        warnings.filterwarnings('ignore')
        # Calculates the error of the fit parameters given a specified confidence interval
        var_a = fit_parameters_cov_var_matrix[0, 0]
        var_b = fit_parameters_cov_var_matrix[1, 1]
        var_c = fit_parameters_cov_var_matrix[2, 2]

        upper_a = fit_parameters[0] + confidence_interval * np.sqrt(var_a)
        lower_a = fit_parameters[0] - confidence_interval * np.sqrt(var_a)

        upper_b = fit_parameters[1] + confidence_interval * np.sqrt(var_b)
        lower_b = fit_parameters[1] - confidence_interval * np.sqrt(var_b)

        upper_c = fit_parameters[2] + confidence_interval * np.sqrt(var_c)
        lower_c = fit_parameters[2] - confidence_interval * np.sqrt(var_c)

        fit_upper = self.exponential_function_offset(x, *[upper_a, upper_b, upper_c])
        fit_lower = self.exponential_function_offset(x, *[lower_a, lower_b, lower_c])

        return fit_upper, fit_lower, upper_b, lower_b

    def crop_and_rotate(self, image, input_indent, output_indent, interval):
        warnings.filterwarnings('ignore')
        # Crop and rotating of image to exclude input/output facet.
        image_array = np.asarray(image)

        if self.manual == True:
            input_width_index = self.input_width_index
            input_height_index = self.input_height_index
            output_width_index = self.output_width_index
        else:
            input_width_index, input_height_index, output_width_index, output_height_index = self.insertion_detection(
                image.copy(), self.show_plots)

            input_point = (input_width_index, input_height_index)
            output_point = (output_width_index, output_height_index)
            self.set_um_per_pixel(input_point, output_point)

        window_num_pixel_height = np.shape(image_array)[1]  # 2048

        # Cropping of image
        left_indent = input_width_index + input_indent
        right_indent = output_width_index - output_indent
        top_indent = input_height_index - (window_num_pixel_height / 20)

        if top_indent < 0:
            top_indent = 0

        bottom_indent = input_height_index + (window_num_pixel_height / 20)

        if bottom_indent > window_num_pixel_height:
            bottom_indent = window_num_pixel_height

        cropped_image = image.crop((left_indent, top_indent, right_indent, bottom_indent))
        cropped_image_array = np.asarray(cropped_image)

        # Find the waveguide and calculate angle of waveguide
        left_index_guess = 175

        number_of_points = 15

        separation = int((right_indent - left_indent - left_index_guess) / number_of_points)

        angle, angle_params, x_max_index_array, y_max_index_array = self.find_waveguide_angle(cropped_image_array[:, :, 2],left_index_guess, separation,number_of_points)

        # Rotate picture and plot it with the upper and lower limit

        left_indent = left_indent
        right_indent = right_indent
        top_indent = top_indent
        bottom_indent = bottom_indent
        rotated_image = image.rotate(-angle, center=(left_indent, int(angle_params[1]) + top_indent)).crop(
            (left_indent, top_indent, right_indent, bottom_indent))

        rotated_image_array = np.asarray(rotated_image)

        upper = int(angle_params[1] + interval / 2)
        lower = int(angle_params[1] - interval / 2)

        # Convert x array unit from pixels to microns
        x_mu_array = np.arange(np.shape(rotated_image_array)[1]) * self.mum_per_pixel

        return rotated_image_array, x_mu_array, upper, lower

    def analyze_image(self, image, input_indent, output_indent, interval, num_neighbors):
        #The fitting of the image
        warnings.filterwarnings('ignore')
        rotated_image_array, x_mu_array, upper, lower = self.crop_and_rotate(image, input_indent,output_indent, interval)

        cropped_image_height = np.shape(rotated_image_array)[0]

        x = x_mu_array

        # Sum channels to create intensity image
        image_data_raw = np.sum(rotated_image_array, 2)

        cropped_image = image_data_raw[cropped_image_height - upper: cropped_image_height - lower, :]

        # Sum values along the waveguide in an area
        y_raw = np.sum(cropped_image, axis=0)

        # Number of sections to split up the data for the IQR method
        smoothing = 10
        x_iqr, y_iqr, x_blocks = self.remove_outliers_IQR(x, y_raw, smoothing, num_neighbors)

        y_savgol = savgol_filter(y_iqr, 501, 1, mode="nearest")

        if self.show_plots:
            plt.figure(figsize=(10, 6))
            plt.plot(x, y_raw, 'b-', label="Raw data")
            plt.legend()
            plt.xlabel('x Length [um]')
            plt.ylabel('Sum of pixel intensities')
            plt.show()

        fit_x = x_iqr
        fit_y = y_iqr

        initial_guess = [25, 0.0006, np.mean(fit_y[-10:])]
        bounds = ((0, 0, 0), (1000000, 1000000, 1000000))
        fit_parameters, fit_parameters_cov_var_matrix, infodict, mesg, ier, = curve_fit(self.exponential_function_offset,fit_x, fit_y, p0=initial_guess,full_output=True,maxfev=5000, bounds=bounds)

        # fit of exponential function with offset
        fit = self.exponential_function_offset(fit_x, fit_parameters[0], fit_parameters[1], fit_parameters[2])

        residuals = fit_y - self.exponential_function_offset(fit_x, *fit_parameters)
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((fit_y - np.mean(fit_y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot)

        alpha_dB = 10 * np.log10(np.exp(fit_parameters[1] * 1e4))
        alpha_dB_variance = 10 * np.log10(np.exp(np.sqrt(fit_parameters_cov_var_matrix[1, 1]) * 1e4))

        if self.show_plots:
            font_size = 14
            plt.figure(figsize=(10, 6))
            plt.scatter(fit_x, fit_y, alpha=0.2, label="Outlier corrected data", s=4, color="k")
            plt.plot(fit_x, y_savgol, 'r-', label="Smoothed data")
            plt.plot(fit_x, fit, 'b-',
                     label=f"Fit to outlier corrected data: {alpha_dB:.1f} $\\pm$ {alpha_dB_variance:.1f} dB/cm")
            lgnd = plt.legend(fontsize=font_size, scatterpoints=1, frameon=False)
            lgnd.legendHandles[0]._sizes = [30]
            lgnd.legendHandles[0].set_alpha(1)
            plt.xlabel('x Length [um]')
            plt.ylabel('Sum of pixel intensity [a.u.]')
            plt.show()

        return alpha_dB, r_squared, fit_x, fit_y, alpha_dB_variance

    def straight_waveguide(self,image,optimize_parameter):
        IQR_neighbor_removal = 1
        if optimize_parameter:
            input_indent = self.optimize_parameter("left indent", image, 200, 100, 80,IQR_neighbor_removal)
            output_indent = self.optimize_parameter("right indent", image, 200, 100, 80,IQR_neighbor_removal)
            interval = self.optimize_parameter("sum width", image, 200, 100, 80,IQR_neighbor_removal)
        else:
            input_indent = np.int32(input("Enter left indent: "))
            output_indent = np.int32(input("Enter right indent: "))
            interval = np.int32(input("Enter sum width: "))
            IQR_neighbor_removal = np.int32(input("Enter width of removal of IQR: "))

        return self.analyze_image(image, input_indent, output_indent, interval, IQR_neighbor_removal)
################################### SPIRAL #######################################

    def mean_image_intensity(self,image,mum_per_pixel,in_point,out_point):
        #Meaning the image
        warnings.filterwarnings('ignore')
        disk_size = 20
        mean_disk = disk(disk_size)

        mean_image = (rank.mean_percentile(image, footprint=mean_disk, p0=0, p1=1))
        x_path, y_path = self.path_finder(0.1, in_point, out_point, image,mum_per_pixel)
        y_raw = mean_image[y_path, x_path]

        x_image = range(len(y_raw))

        x = np.array([x * mum_per_pixel for x in x_image])

        return x, y_raw

    def find_path(self,bw_image, start, end):
        #Making the cost path image
        warnings.filterwarnings('ignore')
        costs = np.where(bw_image == 1, 1, 10000)
        path, cost = skimage.graph.route_through_array(costs, start=start, end=end, fully_connected=True, geometric=True)
        return path, cost

    def find_input_and_output(self,path):
        #Determining the input/output facet
        warnings.filterwarnings('ignore')
        image = util.img_as_float(imread(path))
        grey_image = image[:, :, 2]

        indent_list = [0, 0.05, 0.9, 1]

        input_indent_start = int(grey_image.shape[1] * indent_list[0])
        input_indent_end = int(grey_image.shape[1] * indent_list[1])

        output_indent_start = int(grey_image.shape[1] * indent_list[2])
        output_indent_end = int(grey_image.shape[1] * indent_list[3])

        input_index = grey_image[:, input_indent_start:input_indent_end] > 0.02

        cy, cx = ndi.center_of_mass(input_index)

        cx = cx + input_indent_start

        input_point = (int(cx), int(cy))

        output_index = grey_image[:, output_indent_start:output_indent_end] > 0.02
        cy, cx = ndi.center_of_mass(output_index)
        cx = grey_image.shape[1] - cx

        output_point = (int(cx), int(cy))

        return input_point, output_point, grey_image


    def um_per_pixel(self,point1, point2, distance):
        warnings.filterwarnings('ignore')

        # calculating Euclidean distance
        dist_pixels = np.linalg.norm(point1 - point2)
        return distance / dist_pixels

    def opt_indent(self,parameter,x_iqr,y_iqr):
        #Optimizing the parameters used in the fitting of the spiral waveguides
        warnings.filterwarnings('ignore')
        font_size = 16
        y_savgol = savgol_filter(y_iqr, 2000, 1)
        #Determining the alpha values for fits of varying parameters.
        indent = np.arange(0, 800, 20)
        dI = indent[1] - indent[0]
        alpha_dB_i = []
        if parameter == "left indent":
            for i in range(1,len(indent)):  # 525
                x_iqr = x_iqr[i:]
                y_savgol = y_savgol[i:]
                fit_x = x_iqr
                intensity_values = y_savgol
                initial_guess = [25, 0.0006, np.min(intensity_values)]
                fit_parameters, fit_parameters_cov_var_matrix, infodict, mesg, ier, = curve_fit(exponential_function_offset,
                                                                                                fit_x,
                                                                                                intensity_values,
                                                                                                p0=initial_guess,
                                                                                                full_output=True,
                                                                                                maxfev=5000)  # sigma=weights, absolute_sigma=True
                alpha_dB = 10 * np.log10(np.exp(fit_parameters[1] * 10))
                alpha_dB_i.append(alpha_dB)
            #Differentiating the alpha values and finding points there the gradient is ~0
            smoothed_alpha = savgol_filter(alpha_dB_i, 4, 1,mode='nearest')
            alpha_indent = np.gradient(smoothed_alpha, dI)
            index_min = []
            abs_tol = 0.01
            while abs_tol < 0.9:
                if len(index_min) == 0:
                    zero_gradient_minus = []
                    zero_gradient_plus = []
                    for i in range(len(alpha_indent) - 1):
                        zero_gradient_p = isclose(alpha_indent[i], alpha_indent[i + 1], abs_tol=abs_tol)
                        zero_gradient_m = isclose(alpha_indent[i], alpha_indent[i - 1], abs_tol=abs_tol)
                        zero_gradient_minus.append(zero_gradient_m)
                        zero_gradient_plus.append(zero_gradient_p)
                        if zero_gradient_plus[i] == True and zero_gradient_minus[i] == True:
                            index_min.append(i)
                abs_tol = abs_tol + 0.01
            #Finding points where the variation in the nearby points are also ~0
            num_neighbors = 1
            point_mean = []
            for index in index_min:
                neighbor_indexes = np.arange(index - num_neighbors, index + num_neighbors + 1, 1)
                neighbor_indexes = [x for x in neighbor_indexes if x > 0 and x < len(alpha_indent)]
                point_m = np.mean(smoothed_alpha[neighbor_indexes])
                point_diff = abs(point_m-smoothed_alpha[index])
                point_mean.append(point_diff)
            min_point_mean = point_mean.index(min(point_mean))
            ideal_indent = indent[index_min[min_point_mean]]
            if self.show_plots:
                plt.figure(figsize=(10, 6))
                plt.plot(indent[:-1], alpha_indent, "k")
                plt.xlabel("Left indents", fontsize=font_size)
                plt.ylabel("d$d\\alpha$/d(indent)", fontsize=font_size)
                plt.axvline(ideal_indent, color="r", linestyle="--",label="Optimized left indent: " + str(ideal_indent))
                plt.legend(["$\\alpha$ values", "Smoothed alpha values", "Optimal indent: " + str(ideal_indent)],fontsize=font_size)
                plt.show()

        elif parameter == "right indent":
            for i in range(1, len(indent)):  # 525
                x_iqr = x_iqr[:-i]
                y_savgol = y_savgol[:-i]
                fit_x = x_iqr
                intensity_values = y_savgol
                initial_guess = [25, 0.0006, np.min(intensity_values)]
                fit_parameters, fit_parameters_cov_var_matrix, infodict, mesg, ier, = curve_fit(exponential_function_offset,
                                                                                                fit_x,
                                                                                                intensity_values,
                                                                                                p0=initial_guess,
                                                                                                full_output=True,
                                                                                                maxfev=5000)  # sigma=weights, absolute_sigma=True
                alpha_dB = 10 * np.log10(np.exp(fit_parameters[1] * 10))
                alpha_dB_i.append(alpha_dB)
            smoothed_alpha = savgol_filter(alpha_dB_i, 4, 1, mode='nearest')
            alpha_indent = np.gradient(smoothed_alpha, dI)
            index_min = []
            abs_tol = 0.01
            while abs_tol < 0.9:
                if len(index_min) == 0:
                    zero_gradient_minus = []
                    zero_gradient_plus = []
                    for i in range(len(alpha_indent) - 1):
                        zero_gradient_p = isclose(alpha_indent[i], alpha_indent[i + 1], abs_tol=abs_tol)
                        zero_gradient_m = isclose(alpha_indent[i], alpha_indent[i - 1], abs_tol=abs_tol)
                        zero_gradient_minus.append(zero_gradient_m)
                        zero_gradient_plus.append(zero_gradient_p)
                        if zero_gradient_plus[i] == True and zero_gradient_minus[i] == True:
                            index_min.append(i)
                abs_tol = abs_tol + 0.01
            num_neighbors = 1
            point_mean = []
            for index in index_min:
                neighbor_indexes = np.arange(index - num_neighbors, index + num_neighbors + 1, 1)
                neighbor_indexes = [x for x in neighbor_indexes if x > 0 and x < len(alpha_indent)]
                point_m = np.mean(smoothed_alpha[neighbor_indexes])
                point_diff = abs(point_m - smoothed_alpha[index])
                point_mean.append(point_diff)
            min_point_mean = point_mean.index(min(point_mean))
            ideal_indent = indent[index_min[min_point_mean]]
            if self.show_plots:
                plt.figure(figsize=(10, 6))
                plt.plot(indent[:-1], alpha_indent, "k")
                plt.xlabel("Right indents", fontsize=font_size)
                plt.ylabel("d$d\\alpha$/d(indent)", fontsize=font_size)
                plt.axvline(ideal_indent, color="r", linestyle="--", label="Optimized right indent: " + str(ideal_indent))
                plt.legend(["$\\alpha$ values", "Smoothed alpha values", "Optimal indent: " + str(ideal_indent)],fontsize=font_size)
                plt.show()
        return ideal_indent


    def path_finder(self,threshold,in_point,out_point,grey_image,mum_per_pixel):
        #Using the cost path image to find the optimal path
        warnings.filterwarnings('ignore')
        sobel_h = ndi.sobel(grey_image, 0)
        sobel_v = ndi.sobel(grey_image, 1)
        magnitude = np.sqrt(sobel_h ** 2 + sobel_v ** 2)
        font_size = 16
        path_length = []
        threshold = np.round(np.linspace(0.01, threshold, 10), 2)
        #Using different threshold values to find different path lengths
        for i in threshold:
            bw_waveguide = grey_image > i
            start = (in_point[1], in_point[0])
            end = (out_point[1], out_point[0])
            path, costs = self.find_path(bw_waveguide, start, end)
            path_length.append(path)
        #Finding the longest path length as it is the correct path
        diff_paths = []
        path_length_mum = []
        for element in path_length:
            sub_length = len(element)
            length_mum = sub_length * mum_per_pixel
            diff_paths.append(sub_length)
            path_length_mum.append(length_mum)

        max_element = max(path_length_mum)
        max_index = path_length_mum.index(max_element)

        x_path = []
        y_path = []
        for i in range(len(path_length[max_index])):
            x_path.append(path_length[max_index][i][1])
            y_path.append(path_length[max_index][i][0])

        plt.figure()
        if self.show_plots:
            plt.plot(*in_point, "ro")
            plt.plot(*out_point, "ro")
            plt.scatter(x_path[::100], y_path[::100], s=16, alpha=1, color="red")
            plt.xlabel("Width [a.u.]", fontsize=font_size)
            plt.ylabel("Height [a.u.]", fontsize=font_size)
            plt.xticks(fontsize=font_size)
            plt.yticks(fontsize=font_size)
            # plt.axis('off')
            plt.imshow(magnitude, cmap="turbo")
        return x_path, y_path


    def spiral_fit(self,x_iqr,y_iqr,x,y_raw,l,r):
        warnings.filterwarnings('ignore')
        font_size = 16
        x_iqr = x_iqr[l:-r]
        y_iqr = y_iqr[l:-r]
        x = x[l:-r]
        y_raw = y_raw[l:-r]

        fit_x = x_iqr

        #Fit to outlier corrected data
        initial_guess = [25, 0.0006, np.min(y_iqr)]
        fit_parameters, fit_parameters_cov_var_matrix, infodict, mesg, ier, = curve_fit(exponential_function_offset, x_iqr,
                                                                                        y_iqr, p0=initial_guess,
                                                                                        full_output=True,
                                                                                        maxfev=5000)  # sigma=weights, absolute_sigma=True
        fit_outlier = exponential_function_offset(x_iqr, fit_parameters[0], fit_parameters[1], fit_parameters[2])

        residuals = y_iqr - exponential_function_offset(fit_x, *fit_parameters)
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y_iqr - np.mean(y_iqr)) ** 2)
        r_squared_outlier = 1 - (ss_res / ss_tot)

        alpha_dB_outlier = 10 * np.log10(np.exp(fit_parameters[1] * 10))
        alpha_dB_outlier_variance = 10 * np.log10(np.exp(np.sqrt(fit_parameters_cov_var_matrix[1, 1]) * 10))


        #Fit to raw data
        initial_guess = [25, 0.0006, np.min(y_raw)]
        fit_parameters, fit_parameters_cov_var_matrix, infodict, mesg, ier, = curve_fit(exponential_function_offset, x,
                                                                                        y_raw, p0=initial_guess,
                                                                                        full_output=True,
                                                                                        maxfev=5000)  # sigma=weights, absolute_sigma=True
        fit_raw = exponential_function_offset(x, fit_parameters[0], fit_parameters[1], fit_parameters[2])
        residuals = y_raw - exponential_function_offset(x, *fit_parameters)
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y_raw - np.mean(y_raw)) ** 2)
        r_squared_raw = 1 - (ss_res / ss_tot)

        alpha_dB_raw = 10 * np.log10(np.exp(fit_parameters[1] * 10))
        alpha_dB_raw_variance = 10 * np.log10(np.exp(np.sqrt(fit_parameters_cov_var_matrix[1, 1]) * 10))
        if self.show_plots:

            plt.figure()
            plt.plot(x_iqr, fit_outlier, color="#E69F00", linestyle="-", linewidth=3,
                     label=f"Fit to outlier corrected data\n {alpha_dB_outlier:.1f}$\\pm${alpha_dB_outlier_variance:.1f} dB/cm, R\u00b2: {r_squared_outlier:.2f}")  # ,
            plt.plot(x, fit_raw, color="g", linestyle="-", linewidth=3,
                     label=f"Fit to raw data\n {alpha_dB_raw:.1f}$\\pm${alpha_dB_raw_variance:.1f} dB/cm, R\u00b2: {r_squared_raw:.2f}")  # ,
            plt.scatter(x, y_raw, color="#0072B2", s=1.5, label="Raw data")
            plt.scatter(x_iqr, y_iqr, color="#000000", s=1.5, label="Outlier corrected data")
            lgnd = plt.legend(fontsize=14, scatterpoints=1, frameon=False)
            lgnd.legendHandles[2]._sizes = [30]
            lgnd.legendHandles[2].set_alpha(1)
            lgnd.legendHandles[3]._sizes = [30]
            lgnd.legendHandles[3].set_alpha(1)
            plt.xlabel('Propagation length [mm]', fontsize=font_size)
            plt.ylabel('Mean intensity [a.u.]', fontsize=font_size)
            plt.xlim([min(x_iqr), max(x)])
            plt.ylim([min(y_raw), max(y_raw) + 5])
            plt.xticks(fontsize=font_size)
            plt.yticks(fontsize=font_size)
        plt.show()

        return alpha_dB_outlier, alpha_dB_outlier_variance, r_squared_outlier, alpha_dB_raw, alpha_dB_raw_variance,r_squared_raw

    def spiral_waveguide(self,image_directory,distance_um,parameter_optimize):
        warnings.filterwarnings('ignore')
        path = image_directory
        in_point, out_point, grey_image = self.find_input_and_output(path)

        out_point = (out_point[0], out_point[1] + 210)  # (1886,1208)
        in_point = (in_point[0], in_point[1] - 15)  # -80

        point1 = np.array((in_point[0], in_point[1]))
        point2 = np.array((in_point[0], out_point[1]))  # 1985

        mum_per_pixel = self.um_per_pixel(point1, point2, distance_um)

        x, y_raw = self.mean_image_intensity(grey_image, mum_per_pixel,in_point,out_point)

        x_iqr, y_iqr, indexes = self.remove_outliers_IQR(x, y_raw, 10, 1)
        if parameter_optimize:
            l = self.opt_indent("left indent", x_iqr, y_iqr)
            r = self.opt_indent("right indent", x_iqr, y_iqr)
        else:
            l = np.int32(input("Enter left indent: "))
            r = np.int32(input("Enter right indent: "))

        alpha_dB_outlier, alpha_dB_outlier_variance, r_squared_outlier, alpha_dB_raw, alpha_dB_raw_variance,r_squared_raw = self.spiral_fit(x_iqr, y_iqr, x, y_raw, l, r)

        return alpha_dB_outlier, alpha_dB_outlier_variance, r_squared_outlier, alpha_dB_raw, alpha_dB_raw_variance,r_squared_raw
