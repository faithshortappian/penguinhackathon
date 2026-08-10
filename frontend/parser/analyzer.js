/**
 * SAIL Expression Analyzer
 *
 * Performs static analysis on tokenized SAIL expressions to find:
 * - Syntax errors (unmatched brackets, unclosed strings)
 * - Invalid references (unknown function names, bad variable prefixes)
 * - Structural issues (dangling commas, missing arguments)
 * - Provides plain-English explanation of what the expression does
 */

import { TokenType, Tokenizer } from "./tokenizer.js";
import { SAIL_FUNCTIONS } from "./sail-functions.js";

export const Severity = {
  ERROR: "error",
  WARNING: "warning",
  INFO: "info",
};

export class Diagnostic {
  constructor(severity, message, line, column, token = null) {
    this.severity = severity;
    this.message = message;
    this.line = line;
    this.column = column;
    this.token = token;
  }
}

export class AnalysisResult {
  constructor() {
    this.diagnostics = [];
    this.summary = "";
    this.functions = [];
    this.variables = [];
    this.structure = null;
  }

  get errors() {
    return this.diagnostics.filter((d) => d.severity === Severity.ERROR);
  }

  get warnings() {
    return this.diagnostics.filter((d) => d.severity === Severity.WARNING);
  }

  get errorCount() {
    return this.errors.length;
  }
}

export class Analyzer {
  constructor(options = {}) {
    this.knownFunctions = options.knownFunctions || SAIL_FUNCTIONS;
    this.appContext = options.appContext || null; // ApplicationContext from backend
  }

  /**
   * Analyze a SAIL expression string and return diagnostics + summary.
   */
  analyze(source) {
    const result = new AnalysisResult();

    if (!source || !source.trim()) {
      result.summary = "Empty expression.";
      return result;
    }

    // Tokenize
    const tokenizer = new Tokenizer(source);
    let tokens;
    try {
      tokens = tokenizer.tokenize();
    } catch (e) {
      result.diagnostics.push(
        new Diagnostic(Severity.ERROR, `Tokenization failed: ${e.message}`, 1, 1)
      );
      return result;
    }

    // Filter out whitespace/newline/comment tokens for analysis
    const significantTokens = tokens.filter(
      (t) =>
        t.type !== TokenType.WHITESPACE &&
        t.type !== TokenType.NEWLINE &&
        t.type !== TokenType.COMMENT &&
        t.type !== TokenType.EOF
    );

    // Run checks
    this.checkBracketMatching(tokens, result);
    this.checkUnclosedStrings(tokens, result);
    this.checkUnclosedComments(tokens, result);
    this.checkFunctionNames(significantTokens, result);
    this.checkVariableReferences(significantTokens, result);
    this.checkDanglingCommas(significantTokens, result);
    this.checkEmptyParens(significantTokens, result);
    this.checkUnknownTokens(tokens, result);

    // Collect metadata
    result.functions = this.extractFunctions(significantTokens);
    result.variables = this.extractVariables(significantTokens);

    // Generate summary
    result.summary = this.generateSummary(significantTokens, result);

    return result;
  }

  // ─── Bracket Matching ──────────────────────────────────────────

  checkBracketMatching(tokens, result) {
    const stack = [];
    const pairs = {
      [TokenType.OPEN_PAREN]: TokenType.CLOSE_PAREN,
      [TokenType.OPEN_BRACKET]: TokenType.CLOSE_BRACKET,
      [TokenType.OPEN_BRACE]: TokenType.CLOSE_BRACE,
    };
    const names = {
      [TokenType.OPEN_PAREN]: "parenthesis '('",
      [TokenType.CLOSE_PAREN]: "parenthesis ')'",
      [TokenType.OPEN_BRACKET]: "bracket '['",
      [TokenType.CLOSE_BRACKET]: "bracket ']'",
      [TokenType.OPEN_BRACE]: "brace '{'",
      [TokenType.CLOSE_BRACE]: "brace '}'",
    };

    for (const token of tokens) {
      if (pairs[token.type]) {
        stack.push(token);
      } else if (
        token.type === TokenType.CLOSE_PAREN ||
        token.type === TokenType.CLOSE_BRACKET ||
        token.type === TokenType.CLOSE_BRACE
      ) {
        if (stack.length === 0) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              `Unexpected closing ${names[token.type]} with no matching opener`,
              token.line,
              token.column,
              token
            )
          );
        } else {
          const opener = stack.pop();
          if (pairs[opener.type] !== token.type) {
            result.diagnostics.push(
              new Diagnostic(
                Severity.ERROR,
                `Mismatched brackets: opened with ${names[opener.type]} at line ${opener.line} but closed with ${names[token.type]}`,
                token.line,
                token.column,
                token
              )
            );
          }
        }
      }
    }

    // Report unclosed openers
    for (const opener of stack) {
      const names2 = {
        [TokenType.OPEN_PAREN]: "parenthesis '('",
        [TokenType.OPEN_BRACKET]: "bracket '['",
        [TokenType.OPEN_BRACE]: "brace '{'",
      };
      result.diagnostics.push(
        new Diagnostic(
          Severity.ERROR,
          `Unclosed ${names2[opener.type]} — no matching closer found`,
          opener.line,
          opener.column,
          opener
        )
      );
    }
  }

  // ─── Unclosed Strings ──────────────────────────────────────────

  checkUnclosedStrings(tokens, result) {
    for (const token of tokens) {
      if (token.type === TokenType.STRING) {
        if (!token.value.endsWith('"') || token.value.length < 2) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              "Unclosed string literal — missing closing quote",
              token.line,
              token.column,
              token
            )
          );
        }
      }
    }
  }

  // ─── Unclosed Comments ─────────────────────────────────────────

  checkUnclosedComments(tokens, result) {
    for (const token of tokens) {
      if (token.type === TokenType.COMMENT) {
        if (!token.value.endsWith("*/")) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              "Unclosed block comment — missing closing */",
              token.line,
              token.column,
              token
            )
          );
        }
      }
    }
  }

  // ─── Function Name Validation ──────────────────────────────────

  checkFunctionNames(tokens, result) {
    for (let i = 0; i < tokens.length; i++) {
      const token = tokens[i];

      // Check if a function token is followed by '(' — that's a function call
      if (token.type === TokenType.FUNCTION) {
        const next = tokens[i + 1];
        if (next && next.type === TokenType.OPEN_PAREN) {
          const funcName = token.value;
          const prefix = funcName.split("!")[0] + "!";

          // Only validate a! and fn! prefixed functions against known list
          if (prefix === "a!" || prefix === "fn!") {
            if (!this.knownFunctions[funcName]) {
              result.diagnostics.push(
                new Diagnostic(
                  Severity.WARNING,
                  `Unknown function "${funcName}" — check spelling`,
                  token.line,
                  token.column,
                  token
                )
              );
            }
          }
          // rule!, const!, recordType! are user-defined — validate against appContext if available
          else if (prefix === "rule!" && this.appContext) {
            const ruleName = funcName.replace("rule!", "");
            const known = this.appContext.expression_rules?.some(
              (r) => r.name === ruleName
            );
            if (!known) {
              result.diagnostics.push(
                new Diagnostic(
                  Severity.INFO,
                  `Rule reference "${funcName}" not found in loaded application context`,
                  token.line,
                  token.column,
                  token
                )
              );
            }
          }
        }
      }

      // Also check bare identifiers followed by '(' as potential function calls
      if (token.type === TokenType.IDENTIFIER) {
        const next = tokens[i + 1];
        if (next && next.type === TokenType.OPEN_PAREN) {
          const funcName = token.value;
          if (
            this.knownFunctions[funcName] === undefined &&
            !this.looksLikeVariable(funcName)
          ) {
            result.diagnostics.push(
              new Diagnostic(
                Severity.WARNING,
                `Unknown function "${funcName}" — did you mean "fn!${funcName}" or "a!${funcName}"?`,
                token.line,
                token.column,
                token
              )
            );
          }
        }
      }
    }
  }

  // ─── Variable Reference Validation ─────────────────────────────

  checkVariableReferences(tokens, result) {
    const knownPrefixes = [
      "ri!", "local!", "pv!", "pp!", "ac!", "fv!", "rf!", "rv!", "save!",
    ];

    for (const token of tokens) {
      if (token.type === TokenType.VARIABLE) {
        const prefix = token.value.split("!")[0] + "!";
        if (!knownPrefixes.includes(prefix)) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              `Invalid variable prefix "${prefix}" in "${token.value}" — valid prefixes are: ${knownPrefixes.join(", ")}`,
              token.line,
              token.column,
              token
            )
          );
        }

        // Check for empty name after prefix
        const name = token.value.split("!")[1];
        if (!name || name.length === 0) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              `Variable "${token.value}" has no name after the prefix`,
              token.line,
              token.column,
              token
            )
          );
        }
      }

      // Check for potential typos like "ri1" or "locl!" that the tokenizer
      // would have classified as IDENTIFIER
      if (token.type === TokenType.IDENTIFIER) {
        const typoPatterns = [
          { pattern: /^ri\d/, suggestion: "ri!" },
          { pattern: /^loc(a|al|l)$/, suggestion: "local!" },
          { pattern: /^pv\d/, suggestion: "pv!" },
          { pattern: /^pp\d/, suggestion: "pp!" },
        ];

        for (const { pattern, suggestion } of typoPatterns) {
          if (pattern.test(token.value)) {
            result.diagnostics.push(
              new Diagnostic(
                Severity.WARNING,
                `"${token.value}" looks like a typo — did you mean "${suggestion}${token.value.replace(/^[a-z]+\d?/, "")}"?`,
                token.line,
                token.column,
                token
              )
            );
          }
        }
      }
    }
  }

  // ─── Dangling Commas ───────────────────────────────────────────

  checkDanglingCommas(tokens, result) {
    for (let i = 0; i < tokens.length; i++) {
      const token = tokens[i];
      if (token.type === TokenType.COMMA) {
        const next = tokens[i + 1];
        // Comma followed by closing bracket/paren/brace
        if (
          next &&
          (next.type === TokenType.CLOSE_PAREN ||
            next.type === TokenType.CLOSE_BRACKET ||
            next.type === TokenType.CLOSE_BRACE)
        ) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.WARNING,
              "Trailing comma before closing delimiter — this may cause unexpected behavior",
              token.line,
              token.column,
              token
            )
          );
        }

        // Comma at start (after opening bracket/paren)
        const prev = tokens[i - 1];
        if (
          prev &&
          (prev.type === TokenType.OPEN_PAREN ||
            prev.type === TokenType.OPEN_BRACKET ||
            prev.type === TokenType.OPEN_BRACE)
        ) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              "Leading comma after opening delimiter — missing argument",
              token.line,
              token.column,
              token
            )
          );
        }

        // Double comma
        if (next && next.type === TokenType.COMMA) {
          result.diagnostics.push(
            new Diagnostic(
              Severity.ERROR,
              "Double comma — missing argument between commas",
              token.line,
              token.column,
              token
            )
          );
        }
      }
    }
  }

  // ─── Empty Parentheses (for non-zero-arg functions) ────────────

  checkEmptyParens(tokens, result) {
    for (let i = 0; i < tokens.length; i++) {
      const token = tokens[i];
      if (
        token.type === TokenType.OPEN_PAREN &&
        tokens[i + 1]?.type === TokenType.CLOSE_PAREN
      ) {
        // Look back for the function name
        const prev = tokens[i - 1];
        if (prev && (prev.type === TokenType.FUNCTION || prev.type === TokenType.IDENTIFIER)) {
          const funcInfo = this.knownFunctions[prev.value];
          if (funcInfo && funcInfo.minArgs > 0) {
            result.diagnostics.push(
              new Diagnostic(
                Severity.ERROR,
                `"${prev.value}" requires at least ${funcInfo.minArgs} argument(s) but was called with none`,
                prev.line,
                prev.column,
                prev
              )
            );
          }
        }
      }
    }
  }

  // ─── Unknown Tokens ────────────────────────────────────────────

  checkUnknownTokens(tokens, result) {
    for (const token of tokens) {
      if (token.type === TokenType.UNKNOWN) {
        result.diagnostics.push(
          new Diagnostic(
            Severity.WARNING,
            `Unexpected character "${token.value}"`,
            token.line,
            token.column,
            token
          )
        );
      }
    }
  }

  // ─── Metadata Extraction ───────────────────────────────────────

  extractFunctions(tokens) {
    const functions = [];
    for (let i = 0; i < tokens.length; i++) {
      const token = tokens[i];
      if (
        (token.type === TokenType.FUNCTION || token.type === TokenType.IDENTIFIER) &&
        tokens[i + 1]?.type === TokenType.OPEN_PAREN
      ) {
        functions.push(token.value);
      }
    }
    return [...new Set(functions)];
  }

  extractVariables(tokens) {
    const vars = [];
    for (const token of tokens) {
      if (token.type === TokenType.VARIABLE) {
        vars.push(token.value);
      }
    }
    return [...new Set(vars)];
  }

  // ─── Summary Generation ────────────────────────────────────────

  generateSummary(tokens, result) {
    const functions = result.functions;
    const variables = result.variables;
    const parts = [];

    // Determine the outermost construct
    if (functions.length === 0 && variables.length === 0) {
      return "This expression contains only literal values.";
    }

    // Check for interface pattern
    const interfaceComponents = functions.filter((f) => f.startsWith("a!") && !f.includes("local"));
    const hasLocalVars = functions.includes("a!localVariables");
    const hasForEach = functions.includes("a!forEach");

    if (interfaceComponents.length > 0) {
      parts.push(`Builds a UI with: ${interfaceComponents.slice(0, 5).join(", ")}${interfaceComponents.length > 5 ? ` and ${interfaceComponents.length - 5} more components` : ""}.`);
    }

    if (hasLocalVars) {
      const localVars = variables.filter((v) => v.startsWith("local!"));
      if (localVars.length > 0) {
        parts.push(`Defines local variables: ${localVars.join(", ")}.`);
      }
    }

    if (hasForEach) {
      parts.push("Iterates over a list using a!forEach.");
    }

    // Rule inputs
    const ruleInputs = variables.filter((v) => v.startsWith("ri!"));
    if (ruleInputs.length > 0) {
      parts.push(`Accepts inputs: ${ruleInputs.join(", ")}.`);
    }

    // Process variables
    const processVars = variables.filter((v) => v.startsWith("pv!"));
    if (processVars.length > 0) {
      parts.push(`Uses process variables: ${processVars.join(", ")}.`);
    }

    // Query/data functions
    const dataFunctions = functions.filter(
      (f) => f.includes("query") || f.includes("record") || f.includes("Data")
    );
    if (dataFunctions.length > 0) {
      parts.push(`Queries data using: ${dataFunctions.join(", ")}.`);
    }

    // Rule references
    const ruleRefs = functions.filter((f) => f.startsWith("rule!"));
    if (ruleRefs.length > 0) {
      parts.push(`Calls expression rules: ${ruleRefs.join(", ")}.`);
    }

    if (parts.length === 0) {
      parts.push(
        `Uses ${functions.length} function(s) and ${variables.length} variable reference(s).`
      );
    }

    return parts.join(" ");
  }

  // ─── Helpers ───────────────────────────────────────────────────

  looksLikeVariable(name) {
    return /^[a-z]+[A-Z]/.test(name); // camelCase is likely a variable name
  }
}
