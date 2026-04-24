#include "Motor_encoder.h"


void Encoder_Reset(encoder_inst *enc) {
    enc->rpm = 0;
    enc->total_pulses = 0;
    enc->last_counter_value = __HAL_TIM_GET_COUNTER(enc->htim_encoder);
    enc->last_time_ms = HAL_GetTick();
    enc->direction = 1;
    enc->first_time = 1;
}

void Encoder_Update(encoder_inst *enc) {
    uint32_t now = HAL_GetTick();
    uint32_t dt_ms = now - enc->last_time_ms;
    if (dt_ms == 0) return;

    int32_t current_count = __HAL_TIM_GET_COUNTER(enc->htim_encoder);
    int32_t delta_count = current_count - enc->last_counter_value;

    if (delta_count > 32767) delta_count -= ENCODER_RESOLUTION;
    else if (delta_count < -32767) delta_count += ENCODER_RESOLUTION;

    if (__HAL_TIM_IS_TIM_COUNTING_DOWN(enc->htim_encoder)) {
        enc->direction = -1;
    } else {
        enc->direction = 1;
    }

    enc->total_pulses += delta_count;
    enc->rpm = -(((float)delta_count / PULSES_PER_REVOLUTION) * 6000.0f) ;

    enc->last_counter_value = current_count;
    enc->last_time_ms = now;
}
