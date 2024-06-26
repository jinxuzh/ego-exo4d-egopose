import copy
import json
import os

import cv2
import numpy as np
from dataloader import ego_pose_anno_loader
from PIL import Image
from projectaria_tools.core import calibration
from scripts.download import find_annotated_takes
from tqdm import tqdm
from utils.config import create_arg_parse
from utils.reader import PyAvReader
from utils.utils import extract_aria_calib_to_json, get_ego_aria_cam_name


def undistort_aria_img(args):
    # Load all takes metadata
    takes = json.load(open(os.path.join(args.ego4d_data_dir, "takes.json")))

    for anno_type in args.anno_types:
        for split in args.splits:
            # Load GT annotation
            gt_anno_path = os.path.join(
                args.gt_output_dir,
                "annotation",
                anno_type,
                f"ego_pose_gt_anno_{split}_public.json",
            )
            # Check gt-anno file existence
            if not os.path.exists(gt_anno_path):
                print(
                    f"[Warning] Undistortion of aria raw image fails for split={split}({anno_type}). Invalid path: {gt_anno_path}. Skipped for now."
                )
                continue
            gt_anno = json.load(open(gt_anno_path))
            # Input and output root path
            img_view_prefix = "image_portrait_view" if args.portrait_view else "image"
            dist_img_root = os.path.join(
                args.gt_output_dir, img_view_prefix, "distorted", split
            )
            undist_img_root = os.path.join(
                args.gt_output_dir, img_view_prefix, "undistorted", split
            )
            # Extract frames with annotations for all takes
            print("Undisorting Aria images...")
            for i, (take_uid, take_anno) in enumerate(gt_anno.items()):
                # Get current take's metadata
                take = [t for t in takes if t["take_uid"] == take_uid]
                assert len(take) == 1, f"Take: {take_uid} does not exist"
                take = take[0]
                # Get current take's name and aria camera name
                take_name = take["take_name"]
                print(f"[{i+1}/{len(gt_anno)}] processing {take_name}")
                # Get aria calibration model and pinhole camera model
                curr_aria_calib_json_path = os.path.join(
                    args.gt_output_dir, "aria_calib_json", f"{take_name}.json"
                )
                if not os.path.exists(curr_aria_calib_json_path):
                    print(f"No Aria calib json for {take_name}. Skipped.")
                    continue
                aria_rgb_calib = calibration.device_calibration_from_json(
                    curr_aria_calib_json_path
                ).get_camera_calib("camera-rgb")
                pinhole = calibration.get_linear_camera_calibration(512, 512, 150)
                # Input and output directory
                curr_dist_img_dir = os.path.join(dist_img_root, take_name)
                if not os.path.exists(curr_dist_img_dir):
                    print(
                        f"[Warning] No extracted raw aria images found at {curr_dist_img_dir}. Skipped take {take_name}."
                    )
                    continue
                curr_undist_img_dir = os.path.join(undist_img_root, take_name)
                os.makedirs(curr_undist_img_dir, exist_ok=True)
                # Extract undistorted aria images
                for frame_number in tqdm(take_anno.keys(), total=len(take_anno.keys())):
                    f_idx = int(frame_number)
                    curr_undist_img_path = os.path.join(
                        curr_undist_img_dir, f"{f_idx:06d}.jpg"
                    )
                    # Avoid repetitive generation by checking file existence
                    if not os.path.exists(curr_undist_img_path):
                        # Load in distorted images
                        curr_dist_img_path = os.path.join(
                            curr_dist_img_dir, f"{f_idx:06d}.jpg"
                        )
                        assert os.path.exists(
                            curr_dist_img_path
                        ), f"No distorted images found at {curr_dist_img_path}. Please extract images with steps=raw_images first."
                        curr_dist_image = np.array(Image.open(curr_dist_img_path))
                        curr_dist_image = (
                            cv2.rotate(curr_dist_image, cv2.ROTATE_90_COUNTERCLOCKWISE)
                            if args.portrait_view
                            else curr_dist_image
                        )
                        # Undistortion
                        undistorted_image = calibration.distort_by_calibration(
                            curr_dist_image, pinhole, aria_rgb_calib
                        )
                        undistorted_image = (
                            cv2.rotate(undistorted_image, cv2.ROTATE_90_CLOCKWISE)
                            if args.portrait_view
                            else undistorted_image
                        )
                        # Save undistorted image
                        assert cv2.imwrite(
                            curr_undist_img_path, undistorted_image[:, :, ::-1]
                        ), curr_undist_img_path


def extract_aria_img(args):
    # Load all takes metadata
    takes = json.load(open(os.path.join(args.ego4d_data_dir, "takes.json")))

    for anno_type in args.anno_types:
        for split in args.splits:
            # Load GT annotation
            gt_anno_path = os.path.join(
                args.gt_output_dir,
                "annotation",
                anno_type,
                f"ego_pose_gt_anno_{split}_public.json",
            )
            # Check gt-anno file existence
            if not os.path.exists(gt_anno_path):
                print(
                    f"[Warning] Extraction of aria raw image fails for split={split}({anno_type}). Invalid path: {gt_anno_path}. Skipped for now."
                )
                continue
            gt_anno = json.load(open(gt_anno_path))
            # Input and output root path
            take_video_dir = os.path.join(args.ego4d_data_dir, "takes")
            img_view_prefix = "image_portrait_view" if args.portrait_view else "image"
            img_output_root = os.path.join(
                args.gt_output_dir, img_view_prefix, "distorted", split
            )
            os.makedirs(img_output_root, exist_ok=True)
            # Extract frames with annotations for all takes
            print("Extracting Aria images...")
            for i, (take_uid, take_anno) in enumerate(gt_anno.items()):
                # Get current take's metadata
                take = [t for t in takes if t["take_uid"] == take_uid]
                assert len(take) == 1, f"Take: {take_uid} does not exist"
                take = take[0]
                # Get current take's name and aria camera name
                take_name = take["take_name"]
                print(f"[{i+1}/{len(gt_anno)}] processing {take_name}")
                ego_aria_cam_name = get_ego_aria_cam_name(take)
                # Load current take's aria video
                curr_take_video_path = os.path.join(
                    take_video_dir,
                    take_name,
                    "frame_aligned_videos",
                    f"{ego_aria_cam_name}_214-1.mp4",
                )
                if not os.path.exists(curr_take_video_path):
                    print(
                        f"[Warning] No frame aligned videos found at {curr_take_video_path}. Skipped take {take_name}."
                    )
                    continue
                curr_take_img_output_path = os.path.join(img_output_root, take_name)
                os.makedirs(curr_take_img_output_path, exist_ok=True)
                reader = PyAvReader(
                    path=curr_take_video_path,
                    resize=None,
                    mean=None,
                    frame_window_size=1,
                    stride=1,
                    gpu_idx=-1,
                )
                # Extract frames
                for frame_number in tqdm(take_anno.keys(), total=len(take_anno.keys())):
                    f_idx = int(frame_number)
                    out_path = os.path.join(
                        curr_take_img_output_path, f"{f_idx:06d}.jpg"
                    )
                    # Avoid repetitive generation by checking file existence
                    if not os.path.exists(out_path):
                        frame = reader[f_idx][0].cpu().numpy()
                        frame = frame if args.portrait_view else np.rot90(frame)
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        assert cv2.imwrite(out_path, frame), out_path


def save_test_gt_anno(output_dir, gt_anno_private):
    # 1. Save private annotated test JSON file
    with open(
        os.path.join(output_dir, f"ego_pose_gt_anno_test_private.json"), "w"
    ) as f:
        json.dump(gt_anno_private, f)
    # 2. Exclude GT 2D & 3D joints and valid flag information for public un-annotated test file
    gt_anno_public = copy.deepcopy(gt_anno_private)
    for _, take_anno in gt_anno_public.items():
        for _, frame_anno in take_anno.items():
            for k in [
                "left_hand_2d",
                "right_hand_2d",
                "left_hand_3d",
                "right_hand_3d",
                "left_hand_valid_3d",
                "right_hand_valid_3d",
            ]:
                frame_anno.pop(k)
    # 3. Save public un-annotated test JSON file
    with open(os.path.join(output_dir, f"ego_pose_gt_anno_test_public.json"), "w") as f:
        json.dump(gt_anno_public, f)


def create_gt_anno(args):
    """
    Creates ground truth annotation file for train, val and test split. For
    test split creates two versions:
    - public: doesn't have GT 3D joints and valid flag information, used for
    public to do local inference
    - private: has GT 3D joints and valid flag information, used for server
    to evaluate model performance
    """
    print("Generating ground truth annotation files...")
    for anno_type in args.anno_types:
        for split in args.splits:
            # For test split, only save manual annotation
            if split == "test" and anno_type == "auto":
                print("[Warning] No test gt-anno will be generated on auto data. Skipped for now.")
            # Get ground truth annotation
            gt_anno = ego_pose_anno_loader(args, split, anno_type)
            gt_anno_output_dir = os.path.join(
                args.gt_output_dir, "annotation", anno_type
            )
            os.makedirs(gt_anno_output_dir, exist_ok=True)
            # Save ground truth JSON file
            if split in ["train", "val"]:
                with open(
                    os.path.join(
                        gt_anno_output_dir, f"ego_pose_gt_anno_{split}_public.json"
                    ),
                    "w",
                ) as f:
                    json.dump(gt_anno.db, f)
            # For test split, create two versions of GT-anno
            else:
                if len(gt_anno.db) == 0:
                    print(
                        "[Warning] No test gt-anno will be generated. Please download public release from shared drive."
                    )
                else:
                    save_test_gt_anno(gt_anno_output_dir, gt_anno.db)


def create_aria_calib(args):
    # Get all annotated takes
    all_local_take_uids = find_annotated_takes(
        args.ego4d_data_dir, args.splits, args.anno_types
    )
    # Create aria calib JSON output directory
    aria_calib_json_output_dir = os.path.join(args.gt_output_dir, "aria_calib_json")
    os.makedirs(aria_calib_json_output_dir, exist_ok=True)

    # Find uid and take info
    takes = json.load(open(os.path.join(args.ego4d_data_dir, "takes.json")))
    take_to_uid = {
        each_take["take_name"]: each_take["take_uid"]
        for each_take in takes
        if each_take["take_uid"] in all_local_take_uids
    }
    assert len(all_local_take_uids) == len(
        take_to_uid
    ), "Some annotation take doesn't have corresponding info in takes.json"
    # Export aria calibration to JSON file
    print("Generating aria calibration JSON file...")
    for take_name, _ in tqdm(take_to_uid.items()):
        # Get aria name
        take = [t for t in takes if t["take_name"] == take_name]
        assert len(take) == 1, f"Take: {take_name} can't be found in takes.json"
        take = take[0]
        aria_cam_name = get_ego_aria_cam_name(take)
        # 1. Generate aria calib JSON file
        vrs_path = os.path.join(
            args.ego4d_data_dir,
            "takes",
            take_name,
            f"{aria_cam_name}_noimagestreams.vrs",
        )
        if not os.path.exists(vrs_path):
            print(
                f"[Warning] No take vrs found at {vrs_path}. Skipped take {take_name}."
            )
            continue
        output_path = os.path.join(aria_calib_json_output_dir, f"{take_name}.json")
        extract_aria_calib_to_json(vrs_path, output_path)
        # 2. Overwrite f, cx, cy parameter from JSON file
        aria_calib_json = json.load(open(output_path))
        # Overwrite f, cx, cy
        all_cam_calib = aria_calib_json["CameraCalibrations"]
        aria_cam_calib = [c for c in all_cam_calib if c["Label"] == "camera-rgb"][0]
        aria_cam_calib["Projection"]["Params"][0] /= 2
        aria_cam_calib["Projection"]["Params"][1] = (
            aria_cam_calib["Projection"]["Params"][1] - 0.5 - 32
        ) / 2
        aria_cam_calib["Projection"]["Params"][2] = (
            aria_cam_calib["Projection"]["Params"][2] - 0.5 - 32
        ) / 2
        # Save updated JSON calib file
        with open(os.path.join(output_path), "w") as f:
            json.dump(aria_calib_json, f)


def main(args):
    for step in args.steps:
        if step == "aria_calib":
            create_aria_calib(args)
        elif step == "gt_anno":
            create_gt_anno(args)
        elif step == "raw_image":
            extract_aria_img(args)
        elif step == "undistorted_image":
            undistort_aria_img(args)


if __name__ == "__main__":
    args = create_arg_parse()
    main(args)
