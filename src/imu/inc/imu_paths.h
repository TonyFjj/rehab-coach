#ifndef IMU_PATHS_H
#define IMU_PATHS_H

/** 数据目录，默认 <可执行文件>/../data，可用环境变量 IMU_DATA_DIR 覆盖 */
const char *imu_get_data_dir(void);

/** assessment_log.csv 完整路径 */
const char *imu_get_assessment_log_path(void);

/** 确保数据目录存在 */
void imu_ensure_data_dir(void);

#endif
