/*
 * moving_avg_filter.c
 *
 *  Created on: May 30, 2025
 *      Author: User
 */
#include "moving_avg_filter.h"

void reset_filter(mov_avg_filter_inst_float* filter_inst){
	filter_inst->counter = 0;
	filter_inst->sum = 0;
	for(int i=0;i<MOV_AVG_LEN; i++){
		filter_inst->buffer[i]=0;
	}
}
void apply_average_filter(mov_avg_filter_inst_float* filter_inst,float input, float* out ){
	filter_inst->sum += input - filter_inst->buffer[filter_inst->counter];
	filter_inst->buffer[filter_inst->counter] = input;
	filter_inst->counter ++;
	if(filter_inst->counter == MOV_AVG_LEN){
		filter_inst->counter = 0;
	}
	filter_inst->out = filter_inst->sum / MOV_AVG_LEN;
	*out = filter_inst->out;
}


