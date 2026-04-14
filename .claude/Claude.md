# 데이터 분석 및 AI 프로젝트 명명/기록 규칙 (v1.0)

이 프로젝트의 모든 파이썬 코드는 아래의 구조적 명명 규칙과 작업 기록 절차를 엄격히 준수해야 한다.

## 1. 변수 접두어 규칙 (Type-Prefix Naming)
모든 변수는 데이터 구조 또는 라이브러리 타입을 나타내는 소문자 접두어로 시작하며, `snake_case`를 사용한다. 한 변수에는 하나의 구조 접두어만 사용한다.

### 분석/AI 전용 접두어
- **df_**: Pandas DataFrame (예: `df_train_data`, `df_test_results`)
- **ser_**: Pandas Series (예: `ser_target_y`, `ser_feature_importance`)
- **np_**: NumPy ndarray (예: `np_input_matrix`, `np_weights`)
- **tensor_**: PyTorch/TF Tensor (예: `tensor_x_batch`, `tensor_gradient`)
- **plt_**: 시각화 객체 (Figure, Axes) (예: `plt_loss_curve`, `plt_scatter_plot`)
- **model_**: 머신러닝/딥러닝 모델 객체 (예: `model_xgb_classifier`, `model_vit_encoder`)
- **path_**: 경로 객체 또는 경로 문자열 (예: `path_raw_csv`, `path_checkpoint_dir`)

### 표준 자료형 접두어
- **int_**: 정수형 (예: `int_epoch_count`, `int_batch_size`)
- **str_**: 문자열 (예: `str_column_name`, `str_model_version`)
- **float_**: 실수형 (예: `float_learning_rate`, `float_accuracy`)
- **bool_**: 불리언 (예: `bool_is_training`, `bool_has_cuda`)
- **list_**: 리스트 (예: `list_feature_names`, `list_history`)
- **dict_**: 딕셔너리 (예: `dict_params_grid`, `dict_label_map`)
- **set_**: 집합 (예: `set_unique_labels`)
- **tuple_**: 튜플 (예: `tuple_input_shape`)

## 2. 클래스 및 상수 규칙
- **클래스명**: 접두어 없이 `PascalCase` 사용 (예: `FeatureEngineer`, `DataPreprocessor`)
- **상수**: 접두어 없이 모든 문자를 대문자로 한 `SCREAMING_SNAKE_CASE` 사용 (예: `RANDOM_SEED`, `MAX_ITERATIONS`)

## 3. 작업 로그 기록 의무 (claudy_log.md)
모든 주요 질문(User Query)과 답변(AI Response)의 핵심 내용을 프로젝트 루트의 `claudy_log.md` 파일에 즉시 업데이트해야 한다.

- **기록 형식**: 
  ### [YYYY-MM-DD HH:mm]
  **Q:** [사용자 질문 요약]
  **A:** [수행된 코드 수정 및 답변 핵심 요약]
  **변경사항**: [수정되거나 생성된 파일 목록]

## 4. 코드 구현 주의사항
- **전역 변수 자제**: 가급적 함수 인자로 전달하며, 부득이할 경우 상수로 처리한다.
- **가변 인자 주의**: 함수 기본 인자로 빈 리스트(`[]`)나 딕셔너리(`{}`)를 절대 사용하지 않는다. (대신 `None` 사용)
- **C-Style 접두어 금지**: `m_`, `g_` 등의 접두어는 사용하지 않으며, 멤버 변수는 항상 `self.`을 붙여 관리한다.