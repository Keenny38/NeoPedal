.pragma library

// Following starts listed under a race before "+n more"
var LATER = 8

// Texts of the Upcoming Races page joined with " · ", empty ones left out
function joined(parts) {
    return parts.filter(function(part) { return part !== undefined && part !== null && part !== "" }).join(" · ")
}

// Personal bests of a race for the compact list: "GT3 1:42.310 · LMP2 1:35.020"
function bestText(personal) {
    if (!personal || !personal.bests)
        return ""
    return joined(personal.bests.map(function(best) { return best.vehicleClass + " " + best.best }))
}
