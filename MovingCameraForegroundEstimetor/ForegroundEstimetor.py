import numpy as np
from VMD.MovingCameraForegroundEstimetor.MathematicalModels import CompensationModel, StatisticalModel
from VMD.MovingCameraForegroundEstimetor.KLTWrapper import KLTWrapper
import cv2


class ForegroundEstimetor:
    """
    Moving camera foreground estimator class, gets a grayscale frame and returns foreground pixels or
    probabilities for pixels tp be foreground
    """
    def __init__(self, num_models:int=2, block_size:int=4, var_init:float=20.0*20.0, var_trim:float=5.0*5.0,
                 lam:float=0.001, theta_v:float=50.0*50.0, age_trim:float=30, theta_s=2, theta_d=2, dynamic=False,
                 calc_probs=False, sensetivity="mixed", smooth=True):
        """
        :param num_models: number of models for each pixel to use, minimum possible value is 2
        :param block_size: the size of a square block in the grid the image dims most be able to divide by this param
        :param var_init: initial value for variance of models
        :param var_trim: lower bound on variance
        :param lam: lambda param for age corretion after compensation
        :param theta_v: thershold for variance for age correction as in eq (15) in the paper
        :param age_trim: upper bound on age value
        :param theta_s: the thershold for chosing models to update as in eq (7) (8) in the paper
        :param theta_d: the threshold for foreground choosing as in eq (16). Not relevant if calc_prob is False
        :param calc_probs: if true, return the probability for each pixel to be foreground, if false return which pixel
                        is foreground using eq (16)
        :param sensetivity: decide when to update the models and when to predict foreground
        3 possible values:
        True: choose foreground then update - more sensitive to changes but also to noise
        False: update then foreground - this is what the paper stats. less sensetive to changes but also to noise
        'mixed': the implementation of the original code. update mean, the foreground, then update vars and ages
        :param smooth: if True smooth frame using gaussian blur
        """
        self.is_first = True

        self.homography_calculator = KLTWrapper()
        self.compensation_models = None
        self.statistical_models = None
        self.model_height = None
        self.model_width = None

        self.num_models = num_models
        self.block_size = block_size
        self.var_init = var_init
        self.var_trim = var_trim
        self.lam = lam
        self.theta_v = theta_v
        self.age_trim = age_trim
        self.theta_s = theta_s
        self.theta_d = theta_d
        self.dynamic = dynamic

        self.calc_probs = calc_probs
        self.sensetivity = sensetivity
        self.smooth = smooth

    def first_pass(self, gray_frame: np.array):
        """
        activate when the frame is the first frame, initialize all the modules
        :param gray_frame: a gray frame
        :return: foreground estimation
        """
        self.is_first = False
        h, w = gray_frame.shape
        if h % self.block_size or w % self.block_size:
            raise IOError("Image dims most be dividable by block_size")
        self.model_height, self.model_width = h // self.block_size, w // self.block_size   # calc num of grid in each axis

        # create models
        self.compensation_models = CompensationModel(self.num_models, self.model_height, self.model_width,
                                                     self.block_size, self.var_init, self.var_trim, self.lam,
                                                     self.theta_v)
        self.statistical_models = StatisticalModel(self.num_models, self.model_height, self.model_width,
                                                   self.block_size, self.var_init, self.var_trim, self.age_trim,
                                                   self.theta_s, self.theta_d, self.dynamic, self.calc_probs,
                                                   self.sensetivity)

        # initialize homography calculator
        self.homography_calculator.init(gray_frame)

        # initialize models
        self.statistical_models.init()
        inited_means, inited_vars, inited_ages = self.statistical_models.get_models()

        com_means, com_vars, com_ages = self.compensation_models.init(inited_means, inited_vars,
                                                                      inited_ages)
        return self.statistical_models.get_foreground(gray_frame, com_means, com_vars, com_ages)

    def get_foreground(self, gray_frame):
        """
        do the full pipeline, calculating forground
        :param gray_frame: a gray frame
        :return: foreground estimation
        """
        if self.is_first:   # if first frame initialize
            return self.first_pass(gray_frame)

        if self.smooth:
            gary_frame = cv2.medianBlur(gray_frame, 5)
            gray_frame = cv2.GaussianBlur(gray_frame, (7, 7), 0)

        # compensate
        prev_means, prev_vars, prev_ages = self.statistical_models.get_models()
        H = self.homography_calculator.RunTrack(gray_frame)
        com_means, com_vars, com_ages = self.compensation_models.compensate(H, prev_means, prev_vars, prev_ages)

        # estimate foreground
        foreground = self.statistical_models.get_foreground(gray_frame, com_means, com_vars, com_ages)
        return foreground

    def __call__(self, gray_frame):
        return self.get_foreground(gray_frame)
