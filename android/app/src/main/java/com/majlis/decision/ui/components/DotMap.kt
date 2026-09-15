package com.majlis.decision.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import com.majlis.decision.ui.theme.Palette

/**
 * خريطة عالم نقطية مبسّطة — نظير «Map Session» في التصميم المرجعي.
 *
 * تُرسم من قناع نصي (كل حرف عمود، وكل سطر خط عرض) بدل مسارات SVG
 * ثقيلة: أخف بكثير، ويكفي للغرض وهو إظهار توزّع التغطية لا الجغرافيا
 * الدقيقة. الرمز `#` يابسة و`.` ماء.
 */
private val WORLD = listOf(
    "..........................................",
    "....####.......######################.....",
    "..#########...##########################..",
    "..##########..##########################..",
    "...########....########################...",
    "....######......###############..#####....",
    ".....####.........###########.....###.....",
    "......###..........#########.......##.....",
    ".......##...........########..............",
    "........#.....###....#####....####........",
    "..............#####...####....######......",
    "...............####....##.....#######.....",
    "................####...##.....#######.....",
    ".................###...##......#####......",
    ".................###...##.......###.......",
    "..................##...##........##.......",
    "..................##....#.........#.......",
    "...................#..............##......",
    "..........................................",
)

/** علامة على الخريطة: إحداثيات نسبية 0..1 وعدد. */
data class MapMarker(val x: Float, val y: Float, val count: Int)

@Composable
fun DotWorldMap(
    markers: List<MapMarker>,
    modifier: Modifier = Modifier,
    landColor: Color = Palette.CardLight.copy(alpha = 0.75f),
    markerColor: Color = Palette.Accent,
    overlay: @Composable BoxScope.() -> Unit = {},
) {
    Box(modifier = modifier) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val columns = WORLD.first().length
            val rows = WORLD.size
            val stepX = size.width / columns
            val stepY = size.height / rows
            val radius = minOf(stepX, stepY) * 0.32f

            WORLD.forEachIndexed { row, line ->
                line.forEachIndexed { column, cell ->
                    if (cell == '#') {
                        drawCircle(
                            color = landColor,
                            radius = radius,
                            center = Offset(
                                x = column * stepX + stepX / 2f,
                                y = row * stepY + stepY / 2f,
                            ),
                        )
                    }
                }
            }
            markers.forEach { drawMarker(it, markerColor) }
        }
        overlay()
    }
}

private fun DrawScope.drawMarker(marker: MapMarker, color: Color) {
    val center = Offset(marker.x * size.width, marker.y * size.height)
    val radius = minOf(size.width, size.height) * 0.055f
    drawCircle(color = color.copy(alpha = 0.25f), radius = radius * 1.7f, center = center)
    drawCircle(color = color, radius = radius, center = center)
}
