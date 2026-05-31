def sort_string_list(lst):
    new_lst = []
    for i in lst:
        new_lst.append(''.join(sorted(i)))
    return new_lst

sets0 = ['a','abc','cde','acde','abcde','z','yz','x','cd']
sets0 = sort_string_list(sets0)

def minimum_index_cover(strings):
    queries = set()
    string_to_queries = {}
    for string in strings:
        prefixes = [string[:i+1] for i in range(len(string))]
        string_to_queries[string] = prefixes
        queries.update(prefixes)
    
    covered_queries = set()
    selected_strings = []

    while covered_queries != queries:
        best_string = max(string_to_queries, key = lambda s: len(set(string_to_queries[s])-covered_queries))
        selected_strings.append(best_string)
        covered_queries.update(string_to_queries[best_string])
    
    return selected_strings

print(minimum_index_cover(sets0))


sets0 = ['a','abc','cde','acde','abcde','z','yz','x','abf','bcde','cd']
sets0 = ['a','abc','cde','acde','abcde','z','yz','x','cd']
sets0 = sort_string_list(sets0)

def find_minimal_sets(sets):
    set_objects = {s: set(s) for s in sets}
    minimal_sets = []
    for current_set, set_obj in set_objects.items():
        is_subset = any(set_obj < other_set_obj for other_set, other_set_obj in set_objects.items() if other_set != current_set)

        if not is_subset:
            minimal_sets.append(current_set)

    sets = set(sets)
    minimal_sets = set(minimal_sets)
    return list(minimal_sets), list(sets-minimal_sets)

print(1, find_minimal_sets(sets0))

def find_all_leaf(sets):
    results = []
    min_set = find_minimal_sets(sets)
    results.append(min_set[0])
    while min_set[1] != []:
        min_set = find_minimal_sets(min_set[1])
        results.append(min_set[0])
    return results

print(2, find_all_leaf(sets0))

import itertools

def sort_string_list(lst):
    new_lst = []
    for i in lst:
        new_lst.append(''.join(sorted(i)))
    return new_lst

def find_longest(lst):
    max_len = -1
    longest = None
    for i in lst:
        if len(i) > max_len:
            max_len = len(i)
            longest = i

    return longest

def find_viable(word, lst):
    viable = []
    for i in lst:
        new_lst = permutation_create(i)
        new_word = permutation_check(word, new_lst)
        if new_word:
            viable.append(new_word)
    return find_longest(viable)

def permutation_create(word):
    lst = []
    for c in itertools.permutations(word):
        lst.append(''.join(c))
    return lst

def permutation_check(word, lst):
    for i in lst:
        if word in i:
            return i
    return None

def find_longest_path(lst, q):
    n = len(lst)
    if n == 0: return []
    if n == 1: return lst[0]
    longest = find_longest(lst[n-1])
    res = [longest]
    for k in range(2, n+1):
        viable = find_viable(longest, lst[n-k])
        longest = viable
        res.append(viable)
    return res

def find_path(lst):
    res = []
    tree_structure = find_all_leaf(lst)
    res.append(find_longest_path(tree_structure,0))
    return res

def find_remain(lst):
    path = find_path(lst)
    return list(set(lst)-set(sort_string_list(find_longest_path(find_all_leaf(lst),0))))
    
def find_all_path(lst):
    res = []
    while lst:
        viable_path = find_path(lst)
        res.extend(viable_path)
        remain_path = find_remain(lst)
        lst = remain_path
    deepest_leaf = res[-1]
    res.pop()
    for leaf in deepest_leaf:
        res.append([leaf])
    return res


if __name__ == '__main__':
    print('Here is one possibility of shortest combination/permutation of indexes:', find_all_path(sets0))
    print('The shortest possible index needed are', len(find_all_path(sets0)))
    print('Here is the longest path:', find_longest_path(find_all_leaf(sets0), 0))