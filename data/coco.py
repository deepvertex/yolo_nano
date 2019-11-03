import os
import torch
import torch.utils.data as data
import torchvision.transforms as transforms

import numpy as np
from PIL import Image

import pycocotools.coco as coco
from transforms.bounding_box import BBox


def pil_loader(path):
    with open(path, 'rb') as f:
        with Image.open(f) as img:
            return img.convert('RGB')

def load_annotation_data(data_file_path):
    with open(data_file_path, 'r') as data_file:
        return json.load(data_file)

def make_dataset(root_path, annotation_path, subset):
    pass


# From https://github.com/yhenon/pytorch-retinanet/blob/master/dataloader.py
class COCO(data.Dataset):
    """Coco dataset."""

    def __init__(
        self, root_path, annotation_path, subset='train', 
        transforms=None, get_loader=pil_loader):
        """
        Args:
            root_path (string): COCO directory.
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        self.root_path = root_path
        self.annotation_path = annotation_path
        self.subset = subset
        self.transforms = transforms
        self.loader = get_loader

        self.coco = coco.COCO(self.annotation_path)
        self.image_ids = self.coco.getImgIds()
        self.load_classes()
        

    def load_classes(self):
        # load class names (name -> label)
        categories = self.coco.loadCats(self.coco.getCatIds())
        categories.sort(key=lambda x: x['id'])

        self.classes = {}
        self.coco_labels = {}
        self.coco_labels_inverse = {}
        for c in categories:
            self.coco_labels[len(self.classes)] = c['id']
            self.coco_labels_inverse[c['id']] = len(self.classes)
            self.classes[c['name']] = len(self.classes)

        # also load the reverse (label -> name)
        self.labels = {}
        for key, value in self.classes.items():
            self.labels[value] = key

    def __len__(self):
        return len(self.image_ids)

    def __getitem__(self, idx):

        image = self.load_image(idx)
        bboxes = BBox.from_xyhw(self.load_annotations(idx), image.size)
        if self.transforms is not None:
            image, bboxes = self.transforms(image, bboxes)
        else:
            bboxes = bboxes.to_tensor()

        targets = torch.zeros((len(bboxes), 6))
        targets[:, 1:] = bboxes
        
        return image, targets

    def load_image(self, image_index):
        image_info = self.coco.loadImgs(self.image_ids[image_index])[0]
        image_path = os.path.join(self.root_path, self.subset, image_info['file_name'])
        image = self.loader(image_path)

        return image

    def load_annotations(self, image_index):
        # get ground truth annotations
        annotations_ids = self.coco.getAnnIds(imgIds=self.image_ids[image_index], iscrowd=False)
        annotations = np.zeros((0, 5))

        # some images appear to miss annotations (like image with id 257034)
        if len(annotations_ids) == 0:
            return annotations

        # parse annotations
        coco_annotations = self.coco.loadAnns(annotations_ids)
        for idx, a in enumerate(coco_annotations):
            # some annotations have basically no width / height, skip them
            if a['bbox'][2] < 1 or a['bbox'][3] < 1:
                continue

            annotation = np.zeros((1, 5))
            annotation[0, 1:] = a['bbox']
            annotation[0, 0] = self.coco_label_to_label(a['category_id'])
            annotations = np.append(annotations, annotation, axis=0)

        # [class, x, y, w, h]
        return annotations

    def coco_label_to_label(self, coco_label):
        return self.coco_labels_inverse[coco_label]


    def label_to_coco_label(self, label):
        return self.coco_labels[label]

    def image_aspect_ratio(self, image_index):
        image = self.coco.loadImgs(self.image_ids[image_index])[0]
        return float(image['width']) / float(image['height'])

    def num_classes(self):
        return 80

    def collate_fn(self, batch):
        images, targets = list(zip(*batch))
        images = torch.stack(images)
        targets = [bboxes for bboxes in targets if bboxes is not None]
        for i, bboxes in enumerate(targets):
            bboxes[:, 0] = i
        targets = torch.cat(targets, 0)
        return images, targets

    def name(self):
        return "COCO"