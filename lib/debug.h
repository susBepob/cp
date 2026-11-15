// Local-only debug printer. Compiled in only when -DLOCAL is set (the cp.py script does this),
// so submissions never contain it and you never need to delete dbg() lines before submitting.
//
//   dbg(n, v, mp);   ->   [line 14] n = 5 | v = {1, 2, 3} | mp = {(1, 2), (3, 4)}
//
// Works on ints, strings, pairs, tuples, and any nested container (vector, set, map, deque...).
#pragma once
#include <bits/stdc++.h>

namespace dbg_impl {

template <class T, class = void> struct is_container : std::false_type {};
template <class T>
struct is_container<T, std::void_t<decltype(std::begin(std::declval<T>()))>> : std::true_type {};

template <class T> void print(const T& x);

template <class A, class B> void print(const std::pair<A, B>& p) {
    std::cerr << '(';
    print(p.first);
    std::cerr << ", ";
    print(p.second);
    std::cerr << ')';
}

template <class... Ts> void print(const std::tuple<Ts...>& t) {
    std::cerr << '(';
    std::apply([](const auto&... xs) {
        int i = 0;
        ((std::cerr << (i++ ? ", " : ""), print(xs)), ...);
    }, t);
    std::cerr << ')';
}

template <class T> void print(const T& x) {
    if constexpr (std::is_convertible_v<T, std::string_view>) {
        std::cerr << '"' << std::string_view(x) << '"';
    } else if constexpr (is_container<T>::value) {
        std::cerr << '{';
        bool first = true;
        for (const auto& e : x) {
            if (!first) std::cerr << ", ";
            first = false;
            print(e);
        }
        std::cerr << '}';
    } else {
        std::cerr << x;
    }
}

inline std::vector<std::string> split_names(const std::string& s) {
    // split "a, f(b, c), d" on top-level commas only
    std::vector<std::string> out;
    std::string cur;
    int depth = 0;
    for (char c : s) {
        if (c == '(' || c == '{' || c == '[' || c == '<') depth++;
        if (c == ')' || c == '}' || c == ']' || c == '>') depth--;
        if (c == ',' && depth == 0) {
            out.push_back(cur);
            cur.clear();
        } else if (!(c == ' ' && cur.empty())) {
            cur += c;
        }
    }
    out.push_back(cur);
    return out;
}

template <class... Ts> void dbg_all(int line, const char* names, const Ts&... xs) {
    auto ns = split_names(names);
    std::cerr << "\033[33m[line " << line << "]\033[0m ";
    int i = 0;
    ((std::cerr << (i ? " | " : "") << ns[i] << " = ", print(xs), i++), ...);
    std::cerr << std::endl;
}

}  // namespace dbg_impl

#define dbg(...) dbg_impl::dbg_all(__LINE__, #__VA_ARGS__, __VA_ARGS__)
