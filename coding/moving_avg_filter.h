/*
 * moving_avg_filter.h
 *
 *  Created on: May 30, 2025
 *      Author: User
 */

#ifndef SRC_MOVING_AVG_FILTER_H_
#define SRC_MOVING_AVG_FILTER_H_
#include"pid_control.h"
#include "stdint.h"

#define MOV_AVG_LEN 20

typedef struct{
	float buffer[MOV_AVG_LEN];
	uint16_t counter;
	float out;
	float sum;
}mov_avg_filter_inst_float;

void reset_filter(mov_avg_filter_inst_float* filter_inst);
void apply_average_filter(mov_avg_filter_inst_float* filter_inst,float input, float* out );
#endif /* SRC_MOVING_AVG_FILTER_H_ */
