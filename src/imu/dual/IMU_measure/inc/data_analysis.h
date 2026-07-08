#ifndef DATA_ANALYSIS_H
#define DATA_ANALYSIS_H

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <time.h>

/* ============================================================
 *  常量定义
 * ============================================================ */
#define SAMPLE_RATE     100.0       // 采样率 100Hz
#define MAX_DATA_LEN    3500        // 最大数据行数 (35秒 @ 100Hz)
#define PI              3.14159265358979323846

/* 滤波器参数 */
#define FILTER_CUTOFF   20.0        // 低通截止频率 20Hz
#define FILTER_SECTIONS 2           // 4阶 = 2个2阶节级联

/* FFT 参数 */
#define FFT_MAX_LEN     4096        // >= MAX_DATA_LEN 的下一个 2^N

/* 运动检测阈值 */
#define MOVEMENT_THRESH 15.0        // 角速度幅值阈值 (deg/s)
#define MIN_REST_FRAMES 100         // 最少静息帧数 (1秒)
#define PREP_FRAMES     500         // 准备阶段帧数 (5秒, 此期间不分析)

/* 评估日志CSV路径 (所有评估结果追加到同一文件) */
#include "imu_paths.h"

/* ============================================================
 *  数据结构定义
 * ============================================================ */

/* 运动阶段索引 —— 数据驱动的相位分割 */
typedef struct {
    int rest_end;        // 静息阶段结束 (= 运动开始)
    int rise_start;      // 抬举阶段开始
    int rise_end;        // 抬举阶段结束 (= 最大角度时刻)
    int hold_start;      // 保持阶段开始
    int hold_end;        // 保持阶段结束
    int lower_start;     // 放下阶段开始
    int lower_end;       // 放下阶段结束
    int valid;           // 阶段检测是否有效 (1=有效, 0=无效)
    int ref_start;       // 参考窗口起始帧 (用于重力矢量参考)
    int ref_count;       // 参考窗口帧数
} MovementPhases;

/* IMU 单帧记录 (含计算派生量) */
typedef struct {
    double timestamp;
    double ax, ay, az;          // 加速度 (m/s^2)
    double wx, wy, wz;          // 角速度 (deg/s)
    double roll, pitch, yaw;    // 欧拉角 (deg)
    double arm_angle;           // 计算所得手臂抬举角 (deg)
    double ang_vel_mag;         // 角速度幅值 (deg/s)
} IMU_Record;

/* 六维度特征指标 */
typedef struct {
    /* 维度一：抬举幅度 */
    double max_angle;           // 最大抬举角度 (deg)
    /* 维度二：运动平滑度 */
    double rmsj;                // 加加速度 RMS (m/s^3)
    /* 维度三：震颤程度 */
    double tremor_ratio;        // 4-12Hz 震颤能量占比
    double pd_tremor_ratio;     // 4-6Hz 帕金森频段能量占比
    /* 维度四：单肢运动对称性 (替代双侧对称性) */
    double asymmetry_index;     // 综合不对称指数 [0,1]
    double vel_corr;            // 上升/下降速度轮廓相关系数
    double temporal_ratio;      // 时间对称比 (理想=0.5)
    double peak_vel_ratio;      // 峰值速度比 (理想=1.0)
    /* 维度五：运动速度 */
    double completion_time;     // 完成时间 (s)
    double peak_ang_vel;        // 峰值角速度 (deg/s)
    /* 维度六：运动耐力 */
    double hold_std;            // 保持阶段角度标准差 (deg)
    double hold_angle_drop;     // 保持阶段角度下降百分比 (%)
} FeatureMetrics;

/* 评分结果 */
typedef struct {
    double score_rom;           // 抬举幅度 0-30
    double score_smooth;        // 运动平滑 0-25
    double score_tremor;        // 震颤程度 0-20
    double score_symmetry;      // 单肢对称 0-15
    double score_speed;         // 运动速度 0-5
    double score_endurance;     // 运动耐力 0-5
    double total_score;         // 综合评分 0-100
    int    level;               // 康复等级 L1-L4
    int    pd_warning;          // 帕金森预警 (1=预警, 0=正常)
} ScoreResult;

/* ============================================================
 *  函数声明
 * ============================================================ */

/* 数据 I/O */
int  read_imu_csv(const char* filename, IMU_Record* data);

/* 信号处理 */
void butterworth_lowpass(const double* input, double* output, int len,
                         double fc, double fs);
void filtfilt(const double* input, double* output, int len,
              double fc, double fs);

/* 运动阶段检测 */
void detect_movement_phases(IMU_Record* data, int len, MovementPhases* phases);

/* 手臂角度计算 (重力矢量法) */
void calc_arm_angle(IMU_Record* data, int len, const MovementPhases* phases);

/* 六维度特征提取 */
void calc_range_of_motion(const IMU_Record* data, int len,
                          const MovementPhases* phases, double* max_angle);
void calc_smoothness(const IMU_Record* data, int len,
                     const MovementPhases* phases, double* rmsj);
void calc_tremor(const IMU_Record* data, int len,
                 const MovementPhases* phases,
                 double* tremor_ratio, double* pd_tremor_ratio);
void calc_intra_symmetry(const IMU_Record* data, int len,
                         const MovementPhases* phases,
                         double* asymmetry_index, double* vel_corr,
                         double* temporal_ratio, double* peak_vel_ratio);
void calc_speed(const IMU_Record* data, int len,
                const MovementPhases* phases,
                double* completion_time, double* peak_ang_vel);
void calc_endurance(const IMU_Record* data, int len,
                    const MovementPhases* phases,
                    double* hold_std, double* hold_angle_drop);

/* FFT (Cooley-Tukey radix-2) */
void fft_radix2(double* real, double* imag, int N);
int  next_power_of_2(int n);

/* 评分计算 */
ScoreResult calculate_single_hand_score(FeatureMetrics features, const MovementPhases* phases);

/* 一站式评估入口 */
void run_single_hand_assessment(const char* csv_filename);

/* 双侧对称性 (维度四替代方案: 真正的双侧对称性) */
void calc_bilateral_symmetry(const IMU_Record* left_data, int lenL,
                             const IMU_Record* right_data, int lenR,
                             const MovementPhases* phasesL,
                             const MovementPhases* phasesR,
                             double* asymmetry_index, double* vel_corr,
                             double* temporal_ratio, double* peak_vel_ratio);

/* 双IMU一站式评估入口 */
void run_dual_hand_assessment(const char* csv_left, const char* csv_right);

#endif
