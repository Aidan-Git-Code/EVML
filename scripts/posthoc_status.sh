#!/usr/bin/env bash
# Print progress of the background post-hoc differential sweep by parsing its
# log (out/posthoc_diff.log). One-shot by default; --watch refreshes until the
# sweep finishes.
#
#   scripts/posthoc_status.sh [--watch] [--log PATH]

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

LOG="out/posthoc_diff.log"
WATCH=0
while [[ $# -gt 0 ]]; do
	case "$1" in
		--watch) WATCH=1; shift;;
		--log) LOG="$2"; shift 2;;
		*) echo "unknown arg: $1" >&2; exit 2;;
	esac
done

if [[ -t 1 ]]; then B=$'\e[1m'; DIM=$'\e[2m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; X=$'\e[0m'
else B=""; DIM=""; G=""; Y=""; R=""; X=""; fi

hms() { local s=$1; printf '%dh%02dm' $((s/3600)) $(((s%3600)/60)); }

report() {
	if [[ ! -f "$LOG" ]]; then echo "no post-hoc log at $LOG"; return 1; fi

	local total done divs nonok startts startep now elapsed per remain eta lastline running
	total=$(grep -m1 -oE 'dirs=[0-9]+' "$LOG" 2>/dev/null | cut -d= -f2)
	lastline=$(grep '^\[' "$LOG" | tail -1)
	done=$(printf '%s' "$lastline" | grep -oE '^\[[0-9]+' | tr -d '[')
	done=${done:-0}; total=${total:-0}
	divs=$(grep -oE 'divs=[0-9]+' "$LOG" 2>/dev/null | cut -d= -f2 | awk '{s+=$1} END{print s+0}')
	nonok=$(grep -c 'rc=' "$LOG" 2>/dev/null); nonok=${nonok:-0}

	startts=$(grep -m1 -oE 'POSTHOC START [^ ]+' "$LOG" | awk '{print $3}')
	running=""; pgrep -f "POSTHOC" >/dev/null 2>&1 && running=1
	if grep -q "POSTHOC DONE" "$LOG"; then state="${G}done${X}"; running=""
	elif [[ -n "$running" ]]; then state="${G}running${X}"
	else state="${R}stopped (not finished)${X}"; fi

	echo "${B}post-hoc differential${X}  ($state)"
	if [[ "$total" -gt 0 ]]; then
		local pct=$(( done * 100 / total ))
		printf '  progress   %s/%s dirs (%d%%)\n' "$done" "$total" "$pct"
	else
		printf '  progress   %s dirs\n' "$done"
	fi
	printf '  divergences %s%s%s\n' "$([[ $divs -gt 0 ]] && printf '%s' "$R" || printf '%s' "$DIM")" "$divs" "$X"
	[[ "$nonok" -gt 0 ]] && printf '  %snon-ok dirs %s%s\n' "$Y" "$nonok" "$X"

	if [[ -n "$startts" ]]; then
		startep=$(date -d "$startts" +%s 2>/dev/null)
		now=$(date +%s)
		if [[ -n "$startep" && "$done" -gt 0 ]]; then
			elapsed=$((now - startep))
			printf '  elapsed    %s\n' "$(hms "$elapsed")"
			# ETA from the recent rate (last up-to-15 dirs), not the cumulative
			# average, which is skewed by any earlier CPU contention.
			remain=$((total - done))
			local recents first_ts last_ts fe le n recent_per
			recents=$(grep '^\[' "$LOG" | tail -15 | awk '{print $2}')
			n=$(printf '%s\n' "$recents" | grep -c .)
			if [[ "$n" -ge 2 ]]; then
				first_ts=$(printf '%s\n' "$recents" | head -1)
				last_ts=$(printf '%s\n' "$recents" | tail -1)
				fe=$(date -d "$first_ts" +%s 2>/dev/null)
				le=$(date -d "$last_ts" +%s 2>/dev/null)
				if [[ -n "$fe" && -n "$le" && "$le" -gt "$fe" ]]; then
					recent_per=$(( (le - fe) / (n - 1) ))
					printf '  recent     %ds/dir (last %s dirs)\n' "$recent_per" "$n"
					[[ -n "$running" && "$remain" -gt 0 ]] && printf '  eta        ~%s for %s more\n' "$(hms $((remain * recent_per)))" "$remain"
				fi
			fi
		fi
	fi
	[[ -n "$lastline" ]] && printf '  %slatest     %s%s\n' "$DIM" "$lastline" "$X"
	return 0
}

if [[ "$WATCH" -eq 1 ]]; then
	while true; do
		clear 2>/dev/null
		report || break
		grep -q "POSTHOC DONE" "$LOG" 2>/dev/null && break
		pgrep -f "POSTHOC" >/dev/null 2>&1 || { echo; echo "(sweep not running)"; break; }
		sleep 10
	done
else
	report
fi
