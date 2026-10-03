package com.reiflix.reiflix_local

import com.reiflix.reiflix_local.ui.mapper.LibraryUiMappers
import com.reiflix.reiflix_local.ui.model.ReiAnixConsumptionState
import com.reiflix.reiflix_local.ui.model.ReiAnixMediaAvailability
import com.reiflix.reiflix_local.ui.model.ReiAnixMetadataAvailability
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LibraryUiMappersTest {

    @Test
    fun animeMappingPreservesIdentityOrderProgressStateAndMetadata() {
        val first = episode(101, 1, 0.0, 1200.0, "unwatched")
        val partial = episode(102, 2, 300.0, 1200.0, "in_progress")
        val completed = episode(103, 3, 1200.0, 1200.0, "completed")
        val watched = episode(104, 4, 1200.0, 1200.0, "watched")
        val source = animeSource(
            id = 10L,
            seasons = listOf(
                mapOf<String, Any?>(
                    "season" to 1,
                    "season_name" to "Temporada 1",
                    "episodes" to listOf(first, partial, completed, watched),
                ),
            ),
        )

        val model = LibraryUiMappers.anime(source)

        assertEquals(10L, model.id)
        assertEquals("Example Anime", model.title)
        assertEquals(2026, model.year)
        assertTrue(model.favorite)
        assertEquals(ReiAnixMetadataAvailability.AVAILABLE, model.metadataAvailability)
        assertEquals("/cache/poster.jpg", model.artwork?.localPath)
        assertEquals(listOf("Ação", "Drama"), model.genres.map { it.name })
        assertEquals(listOf("action", "drama"), model.genres.map { it.id })

        val episodes = model.seasons.single().episodes
        assertEquals(listOf(101L, 102L, 103L, 104L), episodes.map { it.id })
        assertEquals(listOf(1.0, 2.0, 3.0, 4.0), episodes.map { it.number })
        assertEquals(0.0, episodes[0].progressSeconds!!, 0.0)
        assertEquals(ReiAnixConsumptionState.UNWATCHED, episodes[0].consumptionState)
        assertEquals(ReiAnixConsumptionState.IN_PROGRESS, episodes[1].consumptionState)
        assertFalse(episodes[1].isCompleted)
        assertEquals(ReiAnixConsumptionState.COMPLETED, episodes[2].consumptionState)
        assertTrue(episodes[2].isCompleted)
        assertEquals(ReiAnixConsumptionState.WATCHED, episodes[3].consumptionState)
        assertTrue(episodes[3].isCompleted)
        assertEquals("content://media/102", episodes[1].media.reference)
        assertEquals("content://media/102", episodes[1].media.uri)
        assertNull(episodes[1].media.path)
        assertEquals("identity-102", episodes[1].media.mediaIdentity)
        assertEquals("anime:10:season:1", model.seasons.single().stableKey)
    }

    @Test
    fun removedFileKeepsReferenceAndMapsAvailabilityWithoutInventingSourceData() {
        val removed = episode(
            id = 105,
            number = 5,
            progress = 0.0,
            duration = 1200.0,
            state = "unwatched",
            path = "/storage/emulated/0/removed.mkv",
            missing = true,
        )

        val model = LibraryUiMappers.episode(removed)

        assertEquals(ReiAnixMediaAvailability.MISSING, model.media.availability)
        assertEquals("/storage/emulated/0/removed.mkv", model.media.reference)
        assertEquals("/storage/emulated/0/removed.mkv", model.media.path)
        assertNull(model.media.uri)
        assertEquals("identity-105", model.media.mediaIdentity)
    }

    @Test
    fun missingMetadataAndArtworkRemainExplicitlyAbsent() {
        val source = animeSource(
            id = 11L,
            meta = emptyMap(),
            genres = emptyList(),
            genreIds = emptyList(),
            seasons = listOf(
                mapOf<String, Any?>(
                    "season" to 1,
                    "episodes" to listOf(episode(111, 1, 0.0, 0.0, "unwatched")),
                ),
            ),
        )

        val model = LibraryUiMappers.anime(source)

        assertEquals(ReiAnixMetadataAvailability.UNRESOLVED, model.metadataAvailability)
        assertNull(model.artwork)
        assertNull(model.year)
        assertTrue(model.genres.isEmpty())
        assertEquals("Episode-1.mkv", model.seasons.single().episodes.single().displayTitle)
        assertNull(model.seasons.single().episodes.single().artwork)
        assertNull(model.seasons.single().episodes.single().media.uri)
    }

    @Test
    fun unknownConsumptionStateDoesNotGetDerivedFromProgress() {
        val source = episode(106, 6, 5.0, 1200.0, "future_state").toMutableMap()
        source.remove("watched")

        val model = LibraryUiMappers.episode(source)

        assertEquals(ReiAnixConsumptionState.UNKNOWN, model.consumptionState)
        assertNull(model.watched)
        assertEquals(5.0, model.progressSeconds!!, 0.0)
        assertEquals("content://media/106", model.media.reference)
    }

    @Test
    fun animeAndEpisodeStableKeysUseExistingIds() {
        val source = animeSource(
            id = 42L,
            seasons = listOf(
                mapOf<String, Any?>(
                    "season" to 3,
                    "episodes" to listOf(episode(4201, 1, 0.0, 100.0, "unwatched")),
                ),
            ),
        )

        val model = LibraryUiMappers.anime(source)

        assertEquals("anime:42", model.stableKey)
        assertEquals("anime:42:season:3", model.seasons.single().stableKey)
        assertEquals(4201L, model.seasons.single().episodes.single().id)
    }

    private fun animeSource(
        id: Long,
        meta: Map<String, Any?> = mapOf(
            "year" to 2026,
            "metadata_status" to "available",
            "cover_cache" to "/cache/poster.jpg",
        ),
        genres: List<String> = listOf("Ação", "Drama"),
        genreIds: List<String> = listOf("action", "drama"),
        seasons: List<Map<String, Any?>>,
    ): Map<String, Any?> = mapOf(
        "id" to id,
        "main_title" to "Example Anime",
        "media_kind" to "series",
        "favorite" to true,
        "meta" to meta,
        "genre_ids" to genreIds,
        "genres" to genres,
        "seasons" to seasons,
        "specials" to emptyList<Map<String, Any?>>(),
        "media_files" to emptyList<Map<String, Any?>>(),
    )

    private fun episode(
        id: Long,
        number: Int,
        progress: Double,
        duration: Double,
        state: String,
        path: String = "content://media/$id",
        missing: Boolean = false,
    ): Map<String, Any?> = mapOf(
        "id" to id,
        "anime_id" to 10L,
        "season" to 1,
        "number" to number,
        "episode_title" to "Episode $number",
        "file_name" to "Episode-$number.mkv",
        "path" to path,
        "media_identity" to "identity-$id",
        "progress" to progress,
        "duration" to duration,
        "watched" to (state == "watched"),
        "consumption_state" to state,
        "missing" to missing,
        "availability_state" to if (missing) "missing" else "available",
    )
}
