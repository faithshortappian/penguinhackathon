/**
 * SAIL Expression Tokenizer
 *
 * Tokenizes Appian SAIL expressions into a stream of typed tokens
 * that the analyzer can work with.
 */

export const TokenType = {
  // Literals
  STRING: "STRING",
  NUMBER: "NUMBER",
  BOOLEAN: "BOOLEAN",
  NULL: "NULL",

  // Identifiers and references
  FUNCTION: "FUNCTION", // e.g., a!textField, fn!append, rule!myRule
  VARIABLE: "VARIABLE", // e.g., ri!input, local!var, pv!processVar
  IDENTIFIER: "IDENTIFIER", // bare identifiers

  // Operators
  OPERATOR: "OPERATOR", // +, -, *, /, =, <>, <, >, <=, >=, &
  LOGICAL: "LOGICAL", // and, or, not

  // Delimiters
  OPEN_PAREN: "OPEN_PAREN",
  CLOSE_PAREN: "CLOSE_PAREN",
  OPEN_BRACKET: "OPEN_BRACKET",
  CLOSE_BRACKET: "CLOSE_BRACKET",
  OPEN_BRACE: "OPEN_BRACE",
  CLOSE_BRACE: "CLOSE_BRACE",
  COMMA: "COMMA",
  COLON: "COLON",
  DOT: "DOT",

  // Special
  COMMENT: "COMMENT",
  WHITESPACE: "WHITESPACE",
  NEWLINE: "NEWLINE",
  EOF: "EOF",
  UNKNOWN: "UNKNOWN",
};

// Known SAIL variable prefixes
const VARIABLE_PREFIXES = [
  "ri!", // rule input
  "local!", // local variable
  "pv!", // process variable
  "pp!", // process property
  "ac!", // activity class (node output)
  "fv!", // function variable
  "rf!", // record field
  "rv!", // record variable
  "save!", // save variable
];

// Known SAIL function domain prefixes
const FUNCTION_PREFIXES = [
  "a!", // appian component/function
  "fn!", // built-in function
  "rule!", // expression rule reference
  "recordType!", // record type reference
  "const!", // constant reference
  "dp!", // decision reference (deprecated)
];

export class Token {
  constructor(type, value, line, column, startIndex) {
    this.type = type;
    this.value = value;
    this.line = line;
    this.column = column;
    this.startIndex = startIndex;
  }
}

export class Tokenizer {
  constructor(source) {
    this.source = source;
    this.pos = 0;
    this.line = 1;
    this.column = 1;
    this.tokens = [];
  }

  tokenize() {
    while (this.pos < this.source.length) {
      const startLine = this.line;
      const startCol = this.column;
      const startPos = this.pos;
      const ch = this.source[this.pos];

      // Whitespace
      if (ch === " " || ch === "\t" || ch === "\r") {
        this.advance();
        continue;
      }

      // Newlines
      if (ch === "\n") {
        this.tokens.push(
          new Token(TokenType.NEWLINE, "\n", startLine, startCol, startPos)
        );
        this.advanceLine();
        continue;
      }

      // Comments: /* ... */
      if (ch === "/" && this.peek(1) === "*") {
        this.tokens.push(this.readBlockComment(startLine, startCol, startPos));
        continue;
      }

      // String literals
      if (ch === '"') {
        this.tokens.push(this.readString(startLine, startCol, startPos));
        continue;
      }

      // Numbers
      if (this.isDigit(ch) || (ch === "-" && this.isDigit(this.peek(1)))) {
        this.tokens.push(this.readNumber(startLine, startCol, startPos));
        continue;
      }

      // Delimiters
      if (ch === "(") {
        this.tokens.push(
          new Token(TokenType.OPEN_PAREN, "(", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === ")") {
        this.tokens.push(
          new Token(TokenType.CLOSE_PAREN, ")", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === "[") {
        this.tokens.push(
          new Token(
            TokenType.OPEN_BRACKET,
            "[",
            startLine,
            startCol,
            startPos
          )
        );
        this.advance();
        continue;
      }
      if (ch === "]") {
        this.tokens.push(
          new Token(
            TokenType.CLOSE_BRACKET,
            "]",
            startLine,
            startCol,
            startPos
          )
        );
        this.advance();
        continue;
      }
      if (ch === "{") {
        this.tokens.push(
          new Token(TokenType.OPEN_BRACE, "{", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === "}") {
        this.tokens.push(
          new Token(TokenType.CLOSE_BRACE, "}", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === ",") {
        this.tokens.push(
          new Token(TokenType.COMMA, ",", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === ":") {
        this.tokens.push(
          new Token(TokenType.COLON, ":", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }
      if (ch === ".") {
        this.tokens.push(
          new Token(TokenType.DOT, ".", startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }

      // Multi-char operators
      if (ch === "<" && this.peek(1) === ">") {
        this.tokens.push(
          new Token(TokenType.OPERATOR, "<>", startLine, startCol, startPos)
        );
        this.advance();
        this.advance();
        continue;
      }
      if (ch === "<" && this.peek(1) === "=") {
        this.tokens.push(
          new Token(TokenType.OPERATOR, "<=", startLine, startCol, startPos)
        );
        this.advance();
        this.advance();
        continue;
      }
      if (ch === ">" && this.peek(1) === "=") {
        this.tokens.push(
          new Token(TokenType.OPERATOR, ">=", startLine, startCol, startPos)
        );
        this.advance();
        this.advance();
        continue;
      }

      // Single-char operators
      if ("+-*/=<>&^".includes(ch)) {
        this.tokens.push(
          new Token(TokenType.OPERATOR, ch, startLine, startCol, startPos)
        );
        this.advance();
        continue;
      }

      // Identifiers, variables, functions, keywords
      if (this.isIdentStart(ch)) {
        this.tokens.push(this.readIdentifier(startLine, startCol, startPos));
        continue;
      }

      // Unknown character
      this.tokens.push(
        new Token(TokenType.UNKNOWN, ch, startLine, startCol, startPos)
      );
      this.advance();
    }

    this.tokens.push(
      new Token(TokenType.EOF, "", this.line, this.column, this.pos)
    );
    return this.tokens;
  }

  readBlockComment(startLine, startCol, startPos) {
    let value = "/*";
    this.advance(); // skip /
    this.advance(); // skip *

    while (this.pos < this.source.length) {
      if (this.source[this.pos] === "*" && this.peek(1) === "/") {
        value += "*/";
        this.advance();
        this.advance();
        return new Token(TokenType.COMMENT, value, startLine, startCol, startPos);
      }
      if (this.source[this.pos] === "\n") {
        value += "\n";
        this.advanceLine();
      } else {
        value += this.source[this.pos];
        this.advance();
      }
    }

    // Unclosed comment — still return what we have
    return new Token(TokenType.COMMENT, value, startLine, startCol, startPos);
  }

  readString(startLine, startCol, startPos) {
    let value = '"';
    this.advance(); // skip opening quote

    while (this.pos < this.source.length) {
      const ch = this.source[this.pos];
      if (ch === '"') {
        // Check for escaped quote (double-quote in SAIL)
        if (this.peek(1) === '"') {
          value += '""';
          this.advance();
          this.advance();
          continue;
        }
        value += '"';
        this.advance();
        return new Token(TokenType.STRING, value, startLine, startCol, startPos);
      }
      if (ch === "\n") {
        value += "\n";
        this.advanceLine();
      } else {
        value += ch;
        this.advance();
      }
    }

    // Unclosed string — return partial token (analyzer will flag this)
    return new Token(TokenType.STRING, value, startLine, startCol, startPos);
  }

  readNumber(startLine, startCol, startPos) {
    let value = "";
    if (this.source[this.pos] === "-") {
      value += "-";
      this.advance();
    }

    while (this.pos < this.source.length && this.isDigit(this.source[this.pos])) {
      value += this.source[this.pos];
      this.advance();
    }

    // Decimal
    if (this.pos < this.source.length && this.source[this.pos] === ".") {
      value += ".";
      this.advance();
      while (this.pos < this.source.length && this.isDigit(this.source[this.pos])) {
        value += this.source[this.pos];
        this.advance();
      }
    }

    return new Token(TokenType.NUMBER, value, startLine, startCol, startPos);
  }

  readIdentifier(startLine, startCol, startPos) {
    let value = "";

    while (
      this.pos < this.source.length &&
      this.isIdentChar(this.source[this.pos])
    ) {
      value += this.source[this.pos];
      this.advance();
    }

    // Check if this is a prefixed identifier (variable or function)
    if (this.pos < this.source.length && this.source[this.pos] === "!") {
      value += "!";
      this.advance();

      // Read the rest of the name after the bang
      while (
        this.pos < this.source.length &&
        this.isIdentChar(this.source[this.pos])
      ) {
        value += this.source[this.pos];
        this.advance();
      }

      // Classify: variable or function
      const prefix = value.split("!")[0] + "!";
      if (VARIABLE_PREFIXES.includes(prefix)) {
        return new Token(TokenType.VARIABLE, value, startLine, startCol, startPos);
      }
      if (FUNCTION_PREFIXES.includes(prefix)) {
        return new Token(TokenType.FUNCTION, value, startLine, startCol, startPos);
      }

      // Unknown prefix — still mark as identifier
      return new Token(TokenType.IDENTIFIER, value, startLine, startCol, startPos);
    }

    // Keywords
    const lower = value.toLowerCase();
    if (lower === "true" || lower === "false") {
      return new Token(TokenType.BOOLEAN, value, startLine, startCol, startPos);
    }
    if (lower === "null") {
      return new Token(TokenType.NULL, value, startLine, startCol, startPos);
    }
    if (lower === "and" || lower === "or" || lower === "not") {
      return new Token(TokenType.LOGICAL, value, startLine, startCol, startPos);
    }

    return new Token(TokenType.IDENTIFIER, value, startLine, startCol, startPos);
  }

  // --- Helpers ---

  advance() {
    this.pos++;
    this.column++;
  }

  advanceLine() {
    this.pos++;
    this.line++;
    this.column = 1;
  }

  peek(offset = 1) {
    const idx = this.pos + offset;
    return idx < this.source.length ? this.source[idx] : null;
  }

  isDigit(ch) {
    return ch >= "0" && ch <= "9";
  }

  isIdentStart(ch) {
    return (
      (ch >= "a" && ch <= "z") ||
      (ch >= "A" && ch <= "Z") ||
      ch === "_"
    );
  }

  isIdentChar(ch) {
    return this.isIdentStart(ch) || this.isDigit(ch);
  }
}
