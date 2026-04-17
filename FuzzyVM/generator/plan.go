// AIingFuzzyVM: strategy-plan support.
// Loads a JSON plan (FUZZYVM_PLAN env var) and overrides strategy weights,
// fork, and banned opcodes before generation begins.

package generator

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/ethereum/go-ethereum/core/vm"
)

type Plan struct {
	PlanID          string                 `json:"plan_id"`
	Objective       string                 `json:"objective"`
	Fork            string                 `json:"fork"`
	Rounds          *RoundsSpec            `json:"rounds,omitempty"`
	Batch           *BatchSpec             `json:"batch,omitempty"`
	StrategyWeights map[string]int         `json:"strategy_weights,omitempty"`
	ParameterHints  map[string]interface{} `json:"parameter_hints,omitempty"`
	Constraints     *Constraints           `json:"constraints,omitempty"`
	SeedHint        *SeedHint              `json:"seed_hint,omitempty"`
	Rationale       string                 `json:"rationale,omitempty"`
	ExpectedSignal  []string               `json:"expected_signal,omitempty"`
}

type RoundsSpec struct {
	Min int `json:"min"`
	Max int `json:"max"`
}

type BatchSpec struct {
	NumTests int `json:"num_tests"`
}

type Constraints struct {
	BannedOpcodes        []string `json:"banned_opcodes,omitempty"`
	RequiredOpcodesAnyOf []string `json:"required_opcodes_any_of,omitempty"`
	AllowedCallOps       []string `json:"allowed_call_ops,omitempty"`
	AllowedPrecompiles   []string `json:"allowed_precompiles,omitempty"`
}

type SeedHint struct {
	Hex   string `json:"hex,omitempty"`
	Notes string `json:"notes,omitempty"`
}

var (
	activePlan    *Plan
	bannedOpcodes map[vm.OpCode]struct{}
)

// ActivePlan returns the currently-loaded plan, or nil for stock behavior.
func ActivePlan() *Plan { return activePlan }

// LoadPlanFromEnv reads the path in FUZZYVM_PLAN, if set. No-op otherwise.
func LoadPlanFromEnv() error {
	path := os.Getenv("FUZZYVM_PLAN")
	if path == "" {
		return nil
	}
	return LoadPlanFile(path)
}

func LoadPlanFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read plan %q: %w", path, err)
	}
	var p Plan
	if err := json.Unmarshal(data, &p); err != nil {
		return fmt.Errorf("parse plan %q: %w", path, err)
	}
	return ApplyPlan(&p)
}

func ApplyPlan(p *Plan) error {
	if p == nil {
		return nil
	}
	activePlan = p

	if p.Fork != "" {
		fork = p.Fork
	}

	bannedOpcodes = map[vm.OpCode]struct{}{}
	if p.Constraints != nil {
		for _, name := range p.Constraints.BannedOpcodes {
			op, ok := opcodeByName(name)
			if !ok {
				return fmt.Errorf("unknown opcode in banned_opcodes: %q", name)
			}
			bannedOpcodes[op] = struct{}{}
		}
	}

	if len(p.StrategyWeights) > 0 {
		all := allStrategies()
		known := map[string]bool{}
		knownList := make([]string, 0, len(all))
		for _, s := range all {
			known[s.String()] = true
			knownList = append(knownList, s.String())
		}
		for n := range p.StrategyWeights {
			if !known[n] {
				return fmt.Errorf("unknown strategy %q in strategy_weights (known: %v)", n, knownList)
			}
		}
		weighted := make([]Strategy, 0, len(all))
		for _, s := range all {
			if w, ok := p.StrategyWeights[s.String()]; ok {
				weighted = append(weighted, &weightedStrategy{inner: s, weight: w})
			} else {
				weighted = append(weighted, s)
			}
		}
		strategies = makeMapNormalized(weighted)
	}

	fmt.Fprintf(os.Stderr, "[FuzzyVM plan] loaded plan_id=%q objective=%q fork=%q banned=%d weighted=%d\n",
		p.PlanID, p.Objective, fork, len(bannedOpcodes), len(p.StrategyWeights))
	return nil
}

func allStrategies() []Strategy {
	out := make([]Strategy, 0, len(basicStrategies)+len(callStrategies)+len(jumpStrategies))
	out = append(out, basicStrategies...)
	out = append(out, callStrategies...)
	out = append(out, jumpStrategies...)
	return out
}

// weightedStrategy wraps an existing strategy with a plan-supplied Importance.
type weightedStrategy struct {
	inner  Strategy
	weight int
}

func (w *weightedStrategy) Execute(env Environment) { w.inner.Execute(env) }
func (w *weightedStrategy) String() string          { return w.inner.String() }
func (w *weightedStrategy) Importance() int {
	switch {
	case w.weight < 1:
		return 1
	case w.weight > 100:
		return 100
	default:
		return w.weight
	}
}

func opcodeByName(name string) (vm.OpCode, bool) {
	name = strings.ToUpper(strings.TrimSpace(name))
	for i := 0; i < 256; i++ {
		op := vm.OpCode(i)
		s := op.String()
		if strings.Contains(s, "not defined") {
			continue
		}
		if s == name {
			return op, true
		}
	}
	return 0, false
}

// makeMapNormalized builds the strategy->bucket map using a weight-sum
// normalization, so that any set of positive weights produces a sane
// distribution across the 256 buckets without byte overflow.
//
// Stock makeMap (strategy.go:52) interprets Importance as a 0-100 absolute
// and multiplies by 2.55 to get buckets. When a plan sets multiple
// strategies to high weights, the cumulative `sum` overflows byte and
// stomps buckets. This variant divides each weight by the total so buckets
// always sum to 256.
func makeMapNormalized(strats []Strategy) map[byte]Strategy {
	total := 0
	for _, s := range strats {
		imp := s.Importance()
		if imp < 1 {
			imp = 1
		}
		total += imp
	}
	if total <= 0 {
		return makeMap(strats)
	}
	m := make(map[byte]Strategy, 256)
	cursor := 0
	for i, s := range strats {
		imp := s.Importance()
		if imp < 1 {
			imp = 1
		}
		buckets := (imp * 256) / total
		if i == len(strats)-1 {
			// Last strategy absorbs rounding remainder so we fill all 256 slots.
			buckets = 256 - cursor
		}
		for j := 0; j < buckets; j++ {
			if cursor >= 256 {
				break
			}
			m[byte(cursor)] = s
			cursor++
		}
	}
	// Fallback fill if any gap remains (shouldn't happen).
	for cursor < 256 {
		m[byte(cursor)] = new(validOpcodeGenerator)
		cursor++
	}
	return m
}

// IsBanned reports whether an opcode has been forbidden by the active plan.
func IsBanned(op vm.OpCode) bool {
	if bannedOpcodes == nil {
		return false
	}
	_, ok := bannedOpcodes[op]
	return ok
}
