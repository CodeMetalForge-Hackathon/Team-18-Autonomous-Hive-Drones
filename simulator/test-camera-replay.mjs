import assert from 'node:assert/strict';
import {formatTime,locateTime} from './frontend/src/timeline.js';
const clips=[{duration:300},{duration:300},{duration:120}];
assert.deepEqual(locateTime(clips,330),{index:1,offset:30,start:300});
assert.deepEqual(locateTime(clips,600),{index:2,offset:0,start:600});
assert.equal(formatTime(66000),'18:20:00');
console.log('Continuous timeline boundaries and time formatting passed.');
