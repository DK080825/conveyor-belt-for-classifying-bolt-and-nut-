/*
 * queue.h
 *
 *  Created on: Nov 26, 2025
 *      Author: User
 */

#ifndef SRC_QUEUE_H_
#define SRC_QUEUE_H_

#include "main.h"

#define QUEUE_SIZE 64

extern uint8_t queue[QUEUE_SIZE];
extern volatile uint8_t head;
extern volatile uint8_t tail;

void Queue_Init();
void Queue_Push(uint8_t data);
uint8_t Queue_Pop(void);
uint8_t Queue_IsEmpty(void);

#endif /* SRC_QUEUE_H_ */
