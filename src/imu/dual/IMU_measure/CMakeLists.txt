cmake_minimum_required(VERSION 3.10)

# 项目名称
project(IMU_measure)

# 设置 C 标准
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# 添加头文件搜索路径
include_directories(${PROJECT_SOURCE_DIR}/inc)

# 收集所有源文件
file(GLOB SOURCES "${PROJECT_SOURCE_DIR}/src/*.c")

# 创建可执行文件
add_executable(IMU_measure ${SOURCES})

# 链接必要的库
target_link_libraries(IMU_measure pthread m)

# 设置编译选项
target_compile_options(IMU_measure PRIVATE -Wall -Wextra -O2)