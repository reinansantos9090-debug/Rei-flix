package com.reiflix.reiflix_local

import org.junit.Assert.assertEquals
import org.junit.Test

class PlayerGesturePolicyTest {
    @Test
    fun horizontalDominatesAndIsNotASeekGesture() {
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Direction.HORIZONTAL,
            NativePlayerActivity.PlayerGesturePolicy.direction(
                dx = 240f,
                dy = 20f,
                touchSlop = 12f,
            ),
        )
    }

    @Test
    fun verticalDominatesOnlyWhenDirectionIsClear() {
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Direction.VERTICAL,
            NativePlayerActivity.PlayerGesturePolicy.direction(
                dx = 12f,
                dy = 180f,
                touchSlop = 12f,
            ),
        )
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Direction.NONE,
            NativePlayerActivity.PlayerGesturePolicy.direction(
                dx = 100f,
                dy = 90f,
                touchSlop = 12f,
            ),
        )
    }

    @Test
    fun movementInsideTouchSlopIsNotAgesture() {
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Direction.NONE,
            NativePlayerActivity.PlayerGesturePolicy.direction(
                dx = 5f,
                dy = 7f,
                touchSlop = 12f,
            ),
        )
    }

    @Test
    fun touchZonesUseRelativeWidth() {
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Side.LEFT,
            NativePlayerActivity.PlayerGesturePolicy.side(100f, 1000),
        )
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Side.CENTER,
            NativePlayerActivity.PlayerGesturePolicy.side(500f, 1000),
        )
        assertEquals(
            NativePlayerActivity.PlayerGesturePolicy.Side.RIGHT,
            NativePlayerActivity.PlayerGesturePolicy.side(900f, 1000),
        )
    }
}
