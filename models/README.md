# 사전학습 모델

| 백엔드 | 사전학습 파일 | 해상도 | 출처 |
| --- | --- | --- | --- |
| `jetson` | SSD-MobileNet-v2 UFF + COCO 라벨 | 300×300 | [jetson-inference 모델 목록](https://github.com/dusty-nv/jetson-inference/blob/45da40a8f3c180191b269f57f736caaa025b8a69/data/networks/models.json) |
| `yolo` | Ultralytics YOLO11n, assets v8.3.0 | 320 기본, 416·640 비교 가능 | [Ultralytics 모델 릴리스](https://github.com/ultralytics/assets/releases/tag/v8.3.0) |
| `tensorrt` | 고정 입력 YOLO11n ONNX에서 장치용 엔진 생성 | 320·416·640 중 준비한 크기 | [TensorRT trtexec](https://github.com/NVIDIA/TensorRT/tree/main/samples/trtexec) |

`manifest.json`에 모델 버전, 라이선스 링크, 배포 URL, SHA-256을 둡니다. SSD 모델 다운로드 후 별도 레지스트리와 라벨을 로컬에 준비합니다. YOLO 어댑터는 가중치에 내장된 클래스 이름을, TensorRT 어댑터는 export한 JSON을 읽습니다. 두 클래스의 출력 이름을 `person`, `dog`로 통일합니다.

~~~bash
./scripts/setup_model.sh jetson
./scripts/setup_model.sh yolo
./scripts/setup_model.sh jetson --from-file /path/to/SSD-Mobilenet-v2.tar.gz
~~~

각 제공자의 라이선스와 원본 학습 자료 사용 조건을 따릅니다. [Ultralytics 라이선스](https://www.ultralytics.com/license) · [SSD 원본 모델 프로젝트](https://github.com/tensorflow/models/tree/master/research/object_detection)
