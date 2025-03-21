# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_data_preparation.ipynb.

# %% auto 0
__all__ = ['CropToContentTransform', 'apply_crop_to_content', 'NormalisationTransform', 'EnhancementTransform',
           'RandomElasticTransformGen', 'NoOpTransform', 'ArrayTransform', 'MyAugmentations', 'enhance_image',
           'normalise_image', 'resize_image_and_bboxes', 'apply_augmentations', 'transform_images',
           'CustomDatasetMapper', 'Bbox', 'convert_annotation', 'df_to_detectron2', 'register_detectron2_dataset',
           'register_datasets', 'create_sampler', 'create_mapper', 'create_dataloader', 'create_dataloader_per_set']

# %% ../nbs/01_data_preparation.ipynb 4
import cv2
import numpy as np
import detectron2.data.detection_utils as utils
from detectron2.data.transforms import Transform, TransformGen
from detectron2.data import transforms as T
from torchvision.transforms import ElasticTransform as TorchElasticTransform
import random
from attrs import define
from typing import List, Tuple, Union
import pywt
import torch
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from detectron2.structures import BoxMode
from detectron2.data import DatasetCatalog, MetadataCatalog
import pandas as pd
from logging import Logger
from detectron2.data import (
    build_detection_test_loader,
    build_detection_train_loader,
    get_detection_dataset_dicts,
)
from detectron2.data.samplers import RepeatFactorTrainingSampler
import os

# %% ../nbs/01_data_preparation.ipynb 6
################ CropToContentTransform NOT USED WITH ROI DATASET ################

class CropToContentTransform(Transform):
    @staticmethod
    def get_biggest_data_rectangle(image: np.ndarray, threshold) -> np.ndarray:
        dilated = cv2.dilate(
            cv2.erode(image, np.ones((10, 10), np.uint8), iterations=1),
            np.ones((10, 10), np.uint8),
            iterations=1,
        )
        _, slice_thres = cv2.threshold(
            dilated,
            threshold,
            255,
            cv2.THRESH_TRIANGLE,
        )
        contours, _ = cv2.findContours(
            slice_thres, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return cv2.boundingRect(max(contours, key=cv2.contourArea))

    def apply_image(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        x, y, w, h = self.get_biggest_data_rectangle(
            img, threshold=10
        )
        self.crop_box = (x, y, w, h)
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return img[y:y+h, x:x+w]

    def apply_coords(self, coords):
        x, y, w, h = self.crop_box
        coords[:, 0] -= x
        coords[:, 1] -= y
        return coords

def apply_crop_to_content(
    crop_to_content_bool: bool, dataset_dict: dict, image_format: str = "BGR"
) -> dict:
    image = utils.read_image(dataset_dict["file_name"], format=image_format)
    if crop_to_content_bool:
        crop_to_content_transform = CropToContentTransform()
        dataset_dict["image"] = crop_to_content_transform.apply_image(image)
        for ann in dataset_dict["annotations"]:
            bbox = ann["bbox"]
            coords = np.array([bbox[:2], bbox[2:]])
            ann["bbox"] = (
                crop_to_content_transform.apply_coords(coords).flatten().tolist()
            )
    else:
        dataset_dict["image"] = image
    return dataset_dict



# %% ../nbs/01_data_preparation.ipynb 8
class NormalisationTransform(Transform):
    def __init__(self, norm_type: str = "zscore"):
        super().__init__()
        self.norm_type = norm_type

    def _zscore_normalisation(self, image: np.ndarray) -> np.ndarray:
        return (image - np.mean(image)) / np.std(image)

    def _minmax_normalisation(self, image: np.ndarray) -> np.ndarray:
        return (image - np.min(image)) / (np.max(image) - np.min(image))

    def _histogram_normalisation(self, image: np.ndarray) -> np.ndarray:
        # Convert to grayscale
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Apply histogram equalization
        equalized_image = cv2.equalizeHist(gray_image)
        return cv2.cvtColor(equalized_image, cv2.COLOR_GRAY2BGR)

    def _minmax_and_center(self, image: np.ndarray) -> np.ndarray:
        minmax_image = self._minmax_normalisation(image)
        centered_image = minmax_image * 2.0 - 1.0
        return centered_image

    def normalise(self, img: np.ndarray) -> np.ndarray:
        if self.norm_type == "zscore":
            return self._zscore_normalisation(img)
        elif self.norm_type == "minmax":
            return self._minmax_normalisation(img)
        elif self.norm_type == "histogram":
            return self._histogram_normalisation(img)
        elif self.norm_type == "minmax_center":
            return self._minmax_and_center(img)
        elif self.norm_type == None:
            return img
        else:
            raise ValueError(f"Unsupported normalization type: {self.norm_type}")

    def apply_image(self, img: np.ndarray) -> np.ndarray:
        return self.normalise(img).astype(np.float32)
    
    def apply_coords(self, coords: np.ndarray):
        return coords

# %% ../nbs/01_data_preparation.ipynb 10
class EnhancementTransform(Transform):
    def __init__(self, enhance_type: str = "clahe"):
        super().__init__()
        self.enhance_type = enhance_type

    def _clahe_enhancement(
        self,
        image: np.ndarray,
        clip_limit: float = 2.0,
        tile_grid_size: int = 8,
    ) -> np.ndarray:
        clahe = cv2.createCLAHE(
            clipLimit=clip_limit, tileGridSize=(tile_grid_size, tile_grid_size)
        )

        return clahe.apply(image)

    def _dwt_enhancement(self, image: np.ndarray) -> np.ndarray:
        return pywt.dwt2(image, "coif5")[0]

    def enhance(self, img: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self.enhance_type == "clahe":
            return self._clahe_enhancement(img)
        elif self.enhance_type == "dwt":
            return self._dwt_enhancement(img)
        elif self.enhance_type == None:
            return img
        else:
            raise ValueError(f"Unsupported normalization type: {self.enhance_type}")

    def apply_image(self, img: np.ndarray) -> np.ndarray:
        return self.enhance(img).astype(np.float32)

    def apply_coords(self, coords: np.ndarray):
        return coords

# %% ../nbs/01_data_preparation.ipynb 12
class RandomElasticTransformGen(TransformGen):
    """
    Random Elastic Transform Generator for Detectron2 using torchvision's ElasticTransform.
    """
    def __init__(self, alpha, sigma, probability=0.5):
        """
        Args:
            alpha (float): Scaling factor for the displacement field.
            sigma (float): Smoothing factor for the displacement field.
            probability (float): Probability of applying the transformation.
        """
        super().__init__()
        self.elastic_transform = TorchElasticTransform(alpha=alpha, sigma=sigma)
        self.probability = probability

    def get_transform(self, img):
        """
        Get the elastic transformation to apply to an image.

        Args:
            img (ndarray): Input image (H, W, C) or (H, W).

        Returns:
            Transform: A Detectron2 Transform.
        """
        if random.random() > self.probability:
            return NoOpTransform()

        # Handle grayscale images by adding a channel dimension
        if len(img.shape) == 2:  # Grayscale (H, W)
            img = np.expand_dims(img, axis=-1)  # (H, W) -> (H, W, 1)

        # Convert image to PyTorch tensor for torchvision ElasticTransform
        img_tensor = torch.tensor(img, dtype=torch.float32).permute(2, 0, 1)  # (H, W, C) -> (C, H, W)

        # Apply ElasticTransform
        transformed_tensor = self.elastic_transform(img_tensor)

        # Convert back to NumPy array
        transformed_img = transformed_tensor.permute(1, 2, 0).numpy()  # (C, H, W) -> (H, W, C)

        # If the original image was grayscale, squeeze the channel dimension
        if transformed_img.shape[-1] == 1:
            transformed_img = np.squeeze(transformed_img, axis=-1)  # (H, W, 1) -> (H, W)

        return ArrayTransform(transformed_img)


class NoOpTransform(Transform):
    """No-operation transform."""
    def apply_image(self, img):
        return img

    def apply_coords(self, coords):
        return coords


class ArrayTransform(Transform):
    """Transforms an image using a precomputed array."""
    def __init__(self, transformed_img):
        """
        Args:
            transformed_img (ndarray): The precomputed transformed image.
        """
        self.transformed_img = transformed_img

    def apply_image(self, img):
        return self.transformed_img

    def apply_coords(self, coords):
        """
        For elastic transforms, you would typically modify this method to
        apply the displacement fields to coordinates (if required).
        """
        return coords

# %% ../nbs/01_data_preparation.ipynb 13
@define
class MyAugmentations:
    @classmethod
    def random_flip(cls, prob=0.5, vertical=False):
        if vertical:
            return T.RandomFlip(prob=prob, vertical=True, horizontal=False)
        return T.RandomFlip(prob=prob, horizontal=True, vertical=False)

    @classmethod
    def random_brightness(cls, mininum=0.9, maximum=2):
        return T.RandomBrightness(intensity_min=mininum, intensity_max=maximum)

    @classmethod
    def random_contrast(cls, mininum=0.3, maximum=2):
        return T.RandomContrast(intensity_min=mininum, intensity_max=maximum)

    @classmethod
    def random_rotation(cls, angle=[0, 90]):
        return T.RandomRotation(angle=angle, sample_style="choice")
    
    @classmethod
    def random_elastic_transform(cls, alpha=1, sigma=50, probability=0.5):
        # TODO: VERIFY THIS
        return RandomElasticTransformGen(alpha=alpha, sigma=sigma, probability=probability)

    @classmethod
    def resize_shortest_edge(
        cls,
        short_edge_range: List[int] = [512, 544, 576, 608, 640],
        max_size: int = 800,
        sample_style: str = "choice",
    ):
        return T.ResizeShortestEdge(
            short_edge_length=short_edge_range,
            max_size=max_size,
            sample_style=sample_style,
        )

# %% ../nbs/01_data_preparation.ipynb 15
def enhance_image(image: np.ndarray, enhance_type: str = "clahe") -> np.ndarray:
    return EnhancementTransform(enhance_type=enhance_type).apply_image(image)


def normalise_image(image: np.ndarray, norm_type: str = "zscore") -> np.ndarray:
    return NormalisationTransform(norm_type=norm_type).apply_image(image)


def resize_image_and_bboxes(
    dataset_dict: dict,
    final_shape: Tuple[int, int] = (512, 512),
    apply_to_image: bool = True,
) -> np.ndarray:
    image = dataset_dict["image"]
    resize_transform = T.ResizeTransform(
        h=image.shape[0],
        w=image.shape[1],
        new_h=final_shape[0],
        new_w=final_shape[1],
    )
    if apply_to_image:
        image = resize_transform.apply_image(image)
    dataset_dict["width"] = image.shape[1]
    dataset_dict["height"] = image.shape[0]
    dataset_dict["image"] = image
    if "annotations" in dataset_dict:
        for ann in dataset_dict["annotations"]:
            bbox = ann["bbox"]
            coords = np.array([bbox[:2], bbox[2:]])
            ann["bbox"] = resize_transform.apply_coords(coords).flatten().tolist()
    return dataset_dict


def apply_augmentations(dataset_dict: dict, augmentations: T.AugmentationList) -> dict:
    image = dataset_dict["image"]
    aug_input = T.AugInput(image=image)
    transforms = augmentations(aug_input)

    image = torch.from_numpy(aug_input.image.copy()).float()
    dataset_dict["image"] = image
    if "annotations" in dataset_dict:
        image_shape = image.shape[:2]
        annos = [
                utils.transform_instance_annotations(
                    obj, transforms, image_shape, keypoint_hflip_indices=None
                )
                for obj in dataset_dict["annotations"]
                if obj.get("iscrowd", 0) == 0
            ]
        instances = utils.annotations_to_instances(
            annos, image_shape, mask_format=None
        )
        dataset_dict["instances"] = utils.filter_empty_instances(instances)
    return dataset_dict


def transform_images(
    dataset_dict: dict,
    image_format: str,
    augmentations: T.AugmentationList,
    crop_to_content: bool = False,
    final_shape: Tuple[int, int] = (512, 512),
    normalisation_type: str = "zscore",
    enhancement_type: str = "clahe",
) -> dict:
    dataset_dict = apply_crop_to_content(
        crop_to_content_bool=crop_to_content,
        dataset_dict=copy.deepcopy(dataset_dict),
        image_format=image_format,
    )
    dataset_dict["image"] = enhance_image(
        dataset_dict["image"], enhance_type=enhancement_type
    )
    dataset_dict["image"] = normalise_image(
        dataset_dict["image"], norm_type=normalisation_type
    )
    if dataset_dict["image"].shape != final_shape:
        dataset_dict = resize_image_and_bboxes(dataset_dict, final_shape=final_shape)
    dataset_dict = apply_augmentations(
        dataset_dict=dataset_dict, augmentations=augmentations
    )
    return dataset_dict


@define
class CustomDatasetMapper:
    is_train: bool
    augmentations: List[Union[T.Augmentation, T.Transform]]
    image_format: str
    crop_to_content: bool
    normalisation_type: str
    enhancement_type: str
    image_final_shape: Tuple[int, int]

    def __call__(self, dataset_dict: dict) -> dict:
        return transform_images(
            dataset_dict=dataset_dict,
            image_format=self.image_format,
            augmentations=T.AugmentationList(self.augmentations),
            crop_to_content=self.crop_to_content,
            final_shape=self.image_final_shape,
            normalisation_type=self.normalisation_type,
            enhancement_type=self.enhancement_type,
        )

# %% ../nbs/01_data_preparation.ipynb 17
@dataclass
class Bbox:
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    label: str
    area: int

    def __post_init__(self):
        # Create a dictionary to map variable names to values
        coord_dict = {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max
        }
        
        # Iterate over the dictionary and check for negative values
        for coord_name, coord_value in coord_dict.items():
            if coord_value < 0:
                # Raise custom BboxValueError with the variable name and value
                raise ValueError(coord_name, coord_value)

    @staticmethod
    def convert(value: float, factor: int) -> int:
        return int(round(value * factor, 0))

    @classmethod
    def from_dict(cls, data: dict) -> "Bbox":
        return cls(
            x_min=data["x_min"],
            y_min=data["y_min"],
            x_max=data["x_max"],
            y_max=data["y_max"],
            label=data["label"],
            area=data["area"]
        )

    def to_dict(self) -> dict:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
            "label": self.label,
            "area": self.area,
        }

    def __str__(self) -> str:
        return str(self.to_dict())

    def rectangle(self, image: np.ndarray) -> np.ndarray:
        cv2.rectangle(image, (self.x_min, self.y_min), (self.x_max, self.y_max), (255, 255, 255), 2)
        return image

# %% ../nbs/01_data_preparation.ipynb 18
def convert_annotation(bbox_list_str):
    try:
        return [Bbox.from_dict(bbox_dict) for bbox_dict in json.loads(bbox_list_str)]
    except json.decoder.JSONDecodeError:
        try:
            return [Bbox.from_dict(eval(bbox_list_str))]
        except SyntaxError:
            return None


def df_to_detectron2(
    dataset_df, data_folders: dict, classes: List[str], roi: bool = False
):

    # if roi:
    #     annotation_str = "CroppedAnnotation"
    # else:
    #     annotation_str = "Annotation"

    annotation_str = "Annotation"

    dataset_df[annotation_str] = dataset_df[annotation_str].apply(
        lambda bbox_list_str: convert_annotation(bbox_list_str)
    )
    dataset_dicts = []
    for idx, row in dataset_df.iterrows():
        record = {}
        if not roi:
            if isinstance(data_folders, dict):
                    
                data_folder = (
                    data_folders["duke"]
                    if "DLDS" in row.Filename
                    else data_folders["garcia_orta"]
                )
            else:
                data_folder = data_folders
        else:
            data_folder = None

        record["file_name"] = (
            str(data_folder / row.ImagePath)
            if data_folder
            else Path(os.getenv("PHD_DATA")) / row.ImagePath
        )
        record["image_id"] = idx
        # if roi:
        #     record["width"] = row.Right - row.Left
        #     record["height"] = row.Bottom - row.Top
        # else:
        #     record["width"] = row.Width
        #     record["height"] = row.Height

        record["width"] = row.Width
        record["height"] = row.Height

        objs = []
        if isinstance(row[annotation_str], list):
            if row[annotation_str] is not None:
                annotations = row[annotation_str]
                for anno in annotations:
                    anno: Bbox = anno
                    obj = {
                        "bbox": [anno.x_min, anno.y_min, anno.x_max, anno.y_max],
                        "bbox_mode": BoxMode.XYXY_ABS,  # Convert to absolute coordinates
                        "category_id": (
                            classes.index(anno.label) if len(classes) == 2 else 0
                        ),
                    }
                    objs.append(obj)
        record["annotations"] = objs
        dataset_dicts.append(record)

    return dataset_dicts


def register_detectron2_dataset(
    dataset_name,
    dataset_df,
    slices_path: dict,
    classes: List[str],
    roi: bool,
):
    dataset_dicts = df_to_detectron2(
        dataset_df, data_folders=slices_path, classes=classes, roi=roi
    )
    DatasetCatalog.register(dataset_name, lambda: dataset_dicts)
    MetadataCatalog.get(dataset_name).set(thing_classes=classes)


def register_datasets(
    dataframe_path: Path,
    classes: List[str],
    logger,
    slices_path: Union[Path, list[Path]],
    roi: bool = False,
    sets: List[str] = ["train", "val"],
    slices_type: str = None,
):
    for set_name in sets:
        try:
            df = pd.read_feather(
                dataframe_path.parent
                / f"data_splitted/{set_name}_{dataframe_path.stem}.feather"
            )
            if slices_type:
                df = df[df.Contrast == slices_type]
            register_detectron2_dataset(
                dataset_name=set_name,
                dataset_df=df,
                slices_path=slices_path,
                classes=classes,
                roi=roi,
            )
        except AssertionError:
            logger.error("Dataset Already Registered.")

# %% ../nbs/01_data_preparation.ipynb 24
def create_sampler(
    dataset_name: str,
    filter_empty: bool,
    logger: Logger,
    repeat_thresh: float = 0.5,
    seed: int = 0,
) -> RepeatFactorTrainingSampler:
    # TODO: CAN IT BE IMPROVED??
    dataset = get_detection_dataset_dicts(
        dataset_name, filter_empty=filter_empty, min_keypoints=0, proposal_files=None
    )
    logger.info(f"Dataset length: {len(dataset)}")
    repeat_factors = RepeatFactorTrainingSampler.repeat_factors_from_category_frequency(
        dataset, repeat_thresh, sqrt=True
    )
    return RepeatFactorTrainingSampler(repeat_factors, seed=seed)


def create_mapper(
    logger: Logger,
    augmentations: List[MyAugmentations],
    is_train: bool = True,
    crop_to_content: bool = False,
    normalisation_type: str = "minmax",
    enhancement_type: str = "clahe",
    final_shape: tuple = (256, 256),
):
    phase = "Training" if is_train else "Validation"
    logger.info(f"{phase} augmentations: {augmentations}")
    return CustomDatasetMapper(
        is_train=is_train,
        augmentations=augmentations,
        image_format="BGR",
        crop_to_content=crop_to_content,
        normalisation_type=normalisation_type,
        image_final_shape=final_shape,
        enhancement_type=enhancement_type,
    )


def create_dataloader(
    name: str,
    mapper: CustomDatasetMapper,
    sampler: RepeatFactorTrainingSampler = None,
    is_train: bool = True,
    num_workers: int = 15,
    imgs_per_batch: int = 12,
):
    arguments = {
        "dataset": DatasetCatalog.get(name),
        "mapper": mapper,
        "num_workers": num_workers,
    }
    if is_train:
        arguments["total_batch_size"] = imgs_per_batch
        arguments["sampler"] = sampler
        loader = build_detection_train_loader
    else:
        arguments["batch_size"] = imgs_per_batch
        loader = build_detection_test_loader
    return loader(**arguments)


def create_dataloader_per_set(
    set_name: str,
    logger: Logger,
    crop_to_content: bool = False,
    normalisation_type: str = "minmax",
    enhancement_type: str = "clahe",
    final_shape: tuple = (256, 256),
    filter_no_annotations: bool = False,
    num_workers: int = 15,
    imgs_per_batch: int = 12,
    augmentations: List[MyAugmentations] = [],
    sampler_repeat_thres: float = 0.5,
    sampler_seed: int = 43,
):
    logger.info(f"Creating dataloader for {set_name}")
    return create_dataloader(
        set_name,
        mapper=create_mapper(
            logger=logger,
            is_train=set_name == "train",
            crop_to_content=crop_to_content,
            normalisation_type=normalisation_type,
            final_shape=tuple(final_shape),
            enhancement_type=enhancement_type,
            augmentations=augmentations,
        ),
        sampler=create_sampler(
            logger=logger,
            dataset_name=set_name,
            filter_empty=filter_no_annotations,
            repeat_thresh=sampler_repeat_thres,
            seed=sampler_seed,
        ),
        is_train=set_name == "train",
        num_workers=num_workers,
        imgs_per_batch=imgs_per_batch,
    )
