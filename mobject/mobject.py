import numpy as np
import operator as op
import os
import copy
from PIL import Image
from colour import Color

from helpers import *


#TODO: Explain array_attrs

class Mobject(object):
    """
    Mathematical Object
    """
    CONFIG = {
        "color"        : WHITE,
        "stroke_width" : DEFAULT_POINT_THICKNESS,
        "name"         : None,
        "dim"          : 3,
        "target"       : None,
    }
    def __init__(self, *submobjects, **kwargs):
        digest_config(self, kwargs)
        if not all(map(lambda m : isinstance(m, Mobject), submobjects)):
            raise Exception("All submobjects must be of type Mobject")
        self.submobjects = list(submobjects)
        self.color = Color(self.color)
        if self.name is None:
            self.name = self.__class__.__name__
        self.init_points()
        self.generate_points()
        self.init_colors()

    def __str__(self):
        return str(self.name)

    def init_points(self):
        self.points = np.zeros((0, self.dim))

    def init_colors(self):
        #For subclasses
        pass

    def generate_points(self):
        #Typically implemented in subclass, unless purposefully left blank
        pass

    def add(self, *mobjects):
        if self in mobjects:
            raise Exception("Mobject cannot contain self")
        self.submobjects = list_update(self.submobjects, mobjects)
        return self

    def add_to_back(self, *mobjects):
        self.remove(*mobjects)
        self.submobjects = list(mobjects) + self.submobjects
        return self

    def remove(self, *mobjects):
        for mobject in mobjects:
            if mobject in self.submobjects:
                self.submobjects.remove(mobject)
        return self

    def get_array_attrs(self):
        return ["points"]

    def digest_mobject_attrs(self):
        """
        Ensures all attributes which are mobjects are included
        in the submobjects list.
        """
        mobject_attrs = filter(
            lambda x : isinstance(x, Mobject),
            self.__dict__.values()
        )
        self.submobjects = list_update(self.submobjects, mobject_attrs)
        return self

    def apply_over_attr_arrays(self, func):
        for attr in self.get_array_attrs():
            setattr(self, attr, func(getattr(self, attr)))
        return self

    def get_image(self, camera = None):
        if camera is None:
            from camera import Camera
            camera = Camera()
        camera.capture_mobject(self)
        return camera.get_image()

    def show(self, camera = None):
        self.get_image(camera = camera).show()

    def save_image(self, name = None):
        self.get_image().save(
            os.path.join(ANIMATIONS_DIR, (name or str(self)) + ".png")
        )

    def copy(self):
        #TODO, either justify reason for shallow copy, or
        #remove this redundancy everywhere
        # return self.deepcopy() 
        copy_mobject = copy.copy(self)
        copy_mobject.points = np.array(self.points)
        copy_mobject.submobjects = [
            submob.copy() for submob in self.submobjects
        ]
        family = self.submobject_family()
        for attr, value in self.__dict__.items():
            if isinstance(value, Mobject) and value in family and value is not self:
                setattr(copy_mobject, attr, value.copy())
        return copy_mobject

    def deepcopy(self):
        return copy.deepcopy(self)

    def generate_target(self, use_deepcopy = False):
        self.target = None #Prevent exponential explosion
        if use_deepcopy:
            self.target = self.deepcopy()
        else:
            self.target = self.copy()
        return self.target

    #### Transforming operations ######

    def apply_to_family(self, func):
        for mob in self.family_members_with_points():
            func(mob)

    def shift(self, *vectors):
        total_vector = reduce(op.add, vectors)
        for mob in self.family_members_with_points():
           mob.points = mob.points.astype('float')
           mob.points += total_vector
        return self

    def scale(self, scale_factor, **kwargs):
        """
        Default behavior is to scale about the center of the mobject.
        The argument about_edge can be a vector, indicating which side of
        the mobject to scale about, e.g., mob.scale(about_edge = RIGHT) 
        scales about mob.get_right().

        Otherwise, if about_point is given a value, scaling is done with
        respect to that point.
        """
        self.apply_points_function_about_point(
            lambda points : scale_factor*points, **kwargs
        )
        return self

    def rotate_about_origin(self, angle, axis = OUT, axes = []):
        return self.rotate(angle, axis, about_point = ORIGIN)

    def rotate(self, angle, axis = OUT, **kwargs):
        rot_matrix = rotation_matrix(angle, axis)
        self.apply_points_function_about_point(
            lambda points : np.dot(points, rot_matrix.T),
            **kwargs
        )
        return self

    def flip(self, axis = UP, **kwargs):
        return self.rotate(TAU/2, axis, **kwargs)

    def stretch(self, factor, dim, **kwargs):
        def func(points):
            points[:,dim] *= factor
            return points
        self.apply_points_function_about_point(func, **kwargs)
        return self

    def apply_function(self, function, **kwargs):
        #Default to applying matrix about the origin, not mobjects center
        if len(kwargs) == 0:
            kwargs["about_point"] = ORIGIN
        self.apply_points_function_about_point(
            lambda points : np.apply_along_axis(function, 1, points),
            **kwargs
        )
        return self

    def apply_matrix(self, matrix, **kwargs):
        #Default to applying matrix about the origin, not mobjects center
        if len(kwargs) == 0:
            kwargs["about_point"] = ORIGIN
        full_matrix = np.identity(self.dim)
        matrix = np.array(matrix)
        full_matrix[:matrix.shape[0],:matrix.shape[1]] = matrix
        self.apply_points_function_about_point(
            lambda points : np.dot(points, full_matrix.T),
            **kwargs
        )
        return self

    def apply_complex_function(self, function, **kwargs):
        return self.apply_function(
            lambda (x, y, z) : complex_to_R3(function(complex(x, y))),
            **kwargs
        )

    def wag(self, direction = RIGHT, axis = DOWN, wag_factor = 1.0):
        for mob in self.family_members_with_points():
            alphas = np.dot(mob.points, np.transpose(axis))
            alphas -= min(alphas)
            alphas /= max(alphas)
            alphas = alphas**wag_factor
            mob.points += np.dot(
                alphas.reshape((len(alphas), 1)),
                np.array(direction).reshape((1, mob.dim))
            )
        return self

    def reverse_points(self):
        for mob in self.family_members_with_points():
            mob.apply_over_attr_arrays(
                lambda arr : np.array(list(reversed(arr)))
            )
        return self

    def repeat(self, count):
        """
        This can make transition animations nicer
        """
        def repeat_array(array):
            return reduce(
                lambda a1, a2 : np.append(a1, a2, axis = 0),
                [array]*count
            )
        for mob in self.family_members_with_points():
            mob.apply_over_attr_arrays(repeat_array)
        return self

    #### In place operations ######
    #Note, much of these are now redundant with default behavior of
    #above methods

    def apply_points_function_about_point(self, func, about_point = None, about_edge = ORIGIN):
        if about_point is None:
            about_point = self.get_critical_point(about_edge)
        for mob in self.family_members_with_points():
            mob.points -= about_point
            mob.points = func(mob.points)
            mob.points += about_point
        return self

    def rotate_in_place(self, angle, axis = OUT, axes = []):
        # redundant with default behavior of rotate now.
        return self.rotate(angle, axis = axis, axes = axes)

    def scale_in_place(self, scale_factor, **kwargs):
        #Redundant with default behavior of scale now.
        return self.scale(scale_factor, **kwargs)

    def scale_about_point(self, scale_factor, point):
        #Redundant with default behavior of scale now.
        return self.scale(scale_factor, about_point = point)

    def pose_at_angle(self, **kwargs):
        self.rotate(TAU/14, RIGHT+UP, **kwargs)
        return self

    #### Positioning methods ####

    def center(self):
        self.shift(-self.get_center())
        return self

    def align_on_border(self, direction, buff = DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        """
        Direction just needs to be a vector pointing towards side or
        corner in the 2d plane.
        """
        target_point = np.sign(direction) * (SPACE_WIDTH, SPACE_HEIGHT, 0)
        point_to_align = self.get_critical_point(direction)
        shift_val = target_point - point_to_align - buff * np.array(direction)
        shift_val = shift_val * abs(np.sign(direction))
        self.shift(shift_val)
        return self

    def to_corner(self, corner = LEFT+DOWN, buff = DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        return self.align_on_border(corner, buff)

    def to_edge(self, edge = LEFT, buff = DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        return self.align_on_border(edge, buff)

    def next_to(self, mobject_or_point,
                direction = RIGHT,
                buff = DEFAULT_MOBJECT_TO_MOBJECT_BUFFER,
                aligned_edge = ORIGIN,
                submobject_to_align = None,
                index_of_submobject_to_align = None,
                ):
        if isinstance(mobject_or_point, Mobject):
            mob = mobject_or_point
            if index_of_submobject_to_align is not None:
                target_aligner = mob[index_of_submobject_to_align]
            else:
                target_aligner = mob
            target_point = target_aligner.get_critical_point(
                aligned_edge + direction
            )
        else:
            target_point = mobject_or_point
        if submobject_to_align is not None:
            aligner = submobject_to_align
        elif index_of_submobject_to_align is not None:
            aligner = self[index_of_submobject_to_align]
        else:
            aligner = self
        point_to_align = aligner.get_critical_point(aligned_edge - direction)
        self.shift(target_point - point_to_align + buff*direction)
        return self

    def align_to(self, mobject_or_point, direction = UP):
        if isinstance(mobject_or_point, Mobject):
            mob = mobject_or_point
            point = mob.get_edge_center(direction)
        else:
            point = mobject_or_point
        diff = point - self.get_edge_center(direction) 
        self.shift(direction*np.dot(diff, direction))
        return self

    def shift_onto_screen(self, **kwargs):
        space_lengths = [SPACE_WIDTH, SPACE_HEIGHT]
        for vect in UP, DOWN, LEFT, RIGHT:
            dim = np.argmax(np.abs(vect))
            buff = kwargs.get("buff", DEFAULT_MOBJECT_TO_EDGE_BUFFER)
            max_val = space_lengths[dim] - buff
            edge_center = self.get_edge_center(vect)
            if np.dot(edge_center, vect) > max_val:
                self.to_edge(vect, **kwargs)
        return self

    def is_off_screen(self):
        if self.get_left()[0] > SPACE_WIDTH:
            return True
        if self.get_right()[0] < -SPACE_WIDTH:
            return True
        if self.get_bottom()[1] > SPACE_HEIGHT:
            return True
        if self.get_top()[1] < -SPACE_HEIGHT:
            return True
        return False

    def stretch_about_point(self, factor, dim, point):
        return self.stretch(factor, dim, about_point = point)

    def stretch_in_place(self, factor, dim):
        #Now redundant with stretch
        return self.stretch(factor, dim)

    def rescale_to_fit(self, length, dim, stretch = False, **kwargs):
        old_length = self.length_over_dim(dim)
        if old_length == 0:
            return self
        if stretch:
            self.stretch(length/old_length, dim, **kwargs)
        else:
            self.scale(length/old_length, **kwargs)
        return self

    def stretch_to_fit_width(self, width, **kwargs):
        return self.rescale_to_fit(width, 0, stretch = True, **kwargs)

    def stretch_to_fit_height(self, height, **kwargs):
        return self.rescale_to_fit(height, 1, stretch = True, **kwargs)

    def scale_to_fit_width(self, width, **kwargs):
        return self.rescale_to_fit(width, 0, stretch = False, **kwargs)

    def scale_to_fit_height(self, height, **kwargs):
        return self.rescale_to_fit(height, 1, stretch = False, **kwargs)

    def scale_to_fit_depth(self, depth, **kwargs):
        return self.rescale_to_fit(depth, 2, stretch = False, **kwargs)

    def space_out_submobjects(self, factor = 1.5, **kwargs):
        self.scale(factor, **kwargs)
        for submob in self.submobjects:
            submob.scale(1./factor)
        return self

    def move_to(self, point_or_mobject, aligned_edge = ORIGIN):
        if isinstance(point_or_mobject, Mobject):
            target = point_or_mobject.get_critical_point(aligned_edge)
        else:
            target = point_or_mobject
        point_to_align = self.get_critical_point(aligned_edge)
        self.shift(target - point_to_align)
        return self

    def replace(self, mobject, dim_to_match = 0, stretch = False):
        if not mobject.get_num_points() and not mobject.submobjects:
            raise Warning("Attempting to replace mobject with no points")
            return self
        if stretch:
            self.stretch_to_fit_width(mobject.get_width())
            self.stretch_to_fit_height(mobject.get_height())
        else:
            self.rescale_to_fit(
                mobject.length_over_dim(dim_to_match),
                dim_to_match,
                stretch = False
            )
        self.shift(mobject.get_center() - self.get_center())
        return self

    def surround(self, mobject, dim_to_match = 0, stretch = False, buffer_factor = 1.2):
        self.replace(mobject, dim_to_match, stretch)
        self.scale_in_place(buffer_factor)

    def position_endpoints_on(self, start, end):
        curr_vect = self.points[-1] - self.points[0]
        if np.all(curr_vect == 0):
            raise Exception("Cannot position endpoints of closed loop")
        target_vect = end - start
        self.scale(np.linalg.norm(target_vect)/np.linalg.norm(curr_vect))
        self.rotate(
            angle_of_vector(target_vect) - \
            angle_of_vector(curr_vect)
        )
        self.shift(start-self.points[0])
        return self

    ## Color functions

    def highlight(self, color = YELLOW_C, family = True):
        """
        Condition is function which takes in one arguments, (x, y, z).
        Here it just recurses to submobjects, but in subclasses this 
        should be further implemented based on the the inner workings
        of color
        """
        if family:
            for submob in self.submobjects:
                submob.highlight(color, family = family)
        return self

    def gradient_highlight(self, *colors):
        self.submobject_gradient_highlight(*colors)
        return self

    def radial_gradient_highlight(self, center = None, radius = 1, inner_color = WHITE, outer_color = BLACK):
        self.submobject_radial_gradient_highlight(center, radius, inner_color, outer_color)
        return self

    def submobject_gradient_highlight(self, *colors):
        if len(colors) == 0:
            raise Exception("Need at least one color")
        elif len(colors) == 1:
            return self.highlight(*colors)

        mobs = self.family_members_with_points()
        new_colors = color_gradient(colors, len(mobs))

        for mob, color in zip(mobs, new_colors):
            mob.highlight(color, family = False)
        return self

    def submobject_radial_gradient_highlight(self, center = None, radius = 1, inner_color = WHITE, outer_color = BLACK):
        mobs = self.family_members_with_points()
        if center == None:
            center = self.get_center()

        for mob in self.family_members_with_points():
            t = np.linalg.norm(mob.get_center() - center)/radius
            t = min(t,1)
            mob_color = interpolate_color(inner_color, outer_color, t)
            mob.highlight(mob_color, family = False)

        return self

    def set_color(self, color):
        self.highlight(color)
        self.color = Color(color)
        return self

    def to_original_color(self):
        self.highlight(self.color)
        return self

    def fade_to(self, color, alpha):
        for mob in self.family_members_with_points():
            start = color_to_rgb(mob.get_color())
            end = color_to_rgb(color)
            new_rgb = interpolate(start, end, alpha)
            mob.highlight(Color(rgb = new_rgb), family = False)
        return self

    def fade(self, darkness = 0.5):
        self.fade_to(BLACK, darkness)
        return self

    def get_color(self):
        return self.color
    ##

    def save_state(self, use_deepcopy = False):
        if hasattr(self, "saved_state"):
            #Prevent exponential growth of data
            self.saved_state = None
        if use_deepcopy:
            self.saved_state = self.deepcopy()
        else:
            self.saved_state = self.copy()
        return self

    def restore(self):
        if not hasattr(self, "saved_state") or self.save_state is None:
            raise Exception("Trying to restore without having saved")
        self.align_data(self.saved_state)
        for sm1, sm2 in zip(self.submobject_family(), self.saved_state.submobject_family()):
            sm1.interpolate(sm1, sm2, 1)
        return self

    ##

    def reduce_across_dimension(self, points_func, reduce_func, dim):
        try:
            points = self.get_points_defining_boundary()
            values = [points_func(points[:, dim])]
        except:
            values = []
        values += [
            mob.reduce_across_dimension(points_func, reduce_func, dim)
            for mob in self.submobjects
        ]
        try:
            return reduce_func(values)
        except:
            return 0

    def get_merged_array(self, array_attr):
        result = None
        for mob in self.family_members_with_points():
            if result is None:
                result = getattr(mob, array_attr)
            else:
                result = np.append(result, getattr(mob, array_attr), 0)
        return result

    def get_all_points(self):
        return self.get_merged_array("points")

    ### Getters ###

    def get_points_defining_boundary(self):
        return self.points

    def get_num_points(self):
        return len(self.points)

    def get_critical_point(self, direction):
        result = np.zeros(self.dim)
        for dim in range(self.dim):
            if direction[dim] <= 0:
                min_point = self.reduce_across_dimension(np.min, np.min, dim)
            if direction[dim] >= 0:
                max_point = self.reduce_across_dimension(np.max, np.max, dim)

            if direction[dim] == 0:
                result[dim] = (max_point+min_point)/2
            elif direction[dim] < 0:
                result[dim] = min_point
            else:
                result[dim] = max_point
        return result

    # Pseudonyms for more general get_critical_point method
    def get_edge_center(self, direction):
        return self.get_critical_point(direction)

    def get_corner(self, direction):
        return self.get_critical_point(direction)

    def get_center(self):
        return self.get_critical_point(np.zeros(self.dim))

    def get_center_of_mass(self):
        return np.apply_along_axis(np.mean, 0, self.get_all_points())

    def get_boundary_point(self, direction):
        all_points = self.get_all_points()
        return all_points[np.argmax(np.dot(all_points, direction))]

    def get_top(self):
        return self.get_edge_center(UP)

    def get_bottom(self):
        return self.get_edge_center(DOWN)

    def get_right(self):
        return self.get_edge_center(RIGHT)

    def get_left(self):
        return self.get_edge_center(LEFT)

    def get_zenith(self):
        return self.get_edge_center(OUT)

    def get_nadir(self):
        return self.get_edge_center(IN)

    def length_over_dim(self, dim):
        return (
            self.reduce_across_dimension(np.max, np.max, dim) -
            self.reduce_across_dimension(np.min, np.min, dim)
        )

    def get_width(self):
        return self.length_over_dim(0)

    def get_height(self):
        return self.length_over_dim(1)

    def get_depth(self):
        return self.length_over_dim(2)

    def point_from_proportion(self, alpha):
        raise Exception("Not implemented")


    ## Family matters

    def __getitem__(self, index):
        return self.split()[index]

    def __iter__(self):
        return iter(self.split())

    def __len__(self):
        return len(self.split())

    def split(self):
        result = [self] if len(self.points) > 0 else []
        return result + self.submobjects

    def submobject_family(self):
        sub_families = map(Mobject.submobject_family, self.submobjects)
        all_mobjects = [self] + list(it.chain(*sub_families))
        return remove_list_redundancies(all_mobjects)

    def family_members_with_points(self):
        return filter(
            lambda m : m.get_num_points() > 0,
            self.submobject_family()
        )

    def arrange_submobjects(self, direction = RIGHT, center = True, **kwargs):
        for m1, m2 in zip(self.submobjects, self.submobjects[1:]):
            m2.next_to(m1, direction, **kwargs)
        if center:
            self.center()
        return self

    def arrange_submobjects_in_grid(self, n_rows = None, n_cols = None, **kwargs):
        submobs = self.submobjects
        if n_rows is None and n_cols is None:
            n_cols = int(np.sqrt(len(submobs)))
            
        if n_rows is not None:
            v1 = RIGHT
            v2 = DOWN
            n = len(submobs) / n_rows
        elif n_cols is not None:
            v1 = DOWN
            v2 = RIGHT
            n = len(submobs) / n_cols
        Group(*[
            Group(*submobs[i:i+n]).arrange_submobjects(v1, **kwargs)
            for i in range(0, len(submobs), n)
        ]).arrange_submobjects(v2, **kwargs)
        return self

    def sort_submobjects(self, point_to_num_func = lambda p : p[0]):
        self.submobjects.sort(
            lambda *mobs : cmp(*[
                point_to_num_func(mob.get_center())
                for mob in mobs
            ])
        )
        return self

    ## Alignment
    def align_data(self, mobject):
        self.align_submobjects(mobject)
        self.align_points(mobject)
        #Recurse
        for m1, m2 in zip(self.submobjects, mobject.submobjects):
            m1.align_data(m2)

    def get_point_mobject(self, center = None):
        """
        The simplest mobject to be transformed to or from self.
        Should by a point of the appropriate type
        """
        raise Exception("Not implemented")

    def align_points(self, mobject):
        count1 = self.get_num_points()
        count2 = mobject.get_num_points()
        if count1 < count2:
            self.align_points_with_larger(mobject)
        elif count2 < count1:
            mobject.align_points_with_larger(self)
        return self

    def align_points_with_larger(self, larger_mobject):
        raise Exception("Not implemented")

    def align_submobjects(self, mobject):
        #If one is empty, and the other is not,
        #push it into its submobject list
        self_has_points, mob_has_points = [
            mob.get_num_points() > 0
            for mob in self, mobject
        ]
        if self_has_points and not mob_has_points:
            mobject.null_point_align(self)
        elif mob_has_points and not self_has_points:
            self.null_point_align(mobject)
        self_count = len(self.submobjects)
        mob_count = len(mobject.submobjects)
        diff = abs(self_count-mob_count)
        if self_count < mob_count:
            self.add_n_more_submobjects(diff)
        elif mob_count < self_count:
            mobject.add_n_more_submobjects(diff)
        return self

    def null_point_align(self, mobject):
        """
        If self has no points, but needs to align
        with mobject, which has points
        """
        if self.submobjects:
            mobject.push_self_into_submobjects()
        else:
            self.points = np.array([mobject.points[0]])
        return self

    def push_self_into_submobjects(self):
        copy = self.copy()
        copy.submobjects = []
        self.init_points()
        self.add(copy)
        return self

    def add_n_more_submobjects(self, n):
        curr = len(self.submobjects)
        if n > 0 and curr == 0:
            self.add(self.copy())
            n -= 1
            curr += 1
        indices = curr*np.arange(curr+n)/(curr+n)
        new_submobjects = []
        for index in indices:
            submob = self.submobjects[index]
            if submob in new_submobjects:
                submob = self.repeat_submobject(submob)
            new_submobjects.append(submob)
        self.submobjects = new_submobjects
        return self

    def repeat_submobject(self, submob):
        return submob.copy()

    def interpolate(self, mobject1, mobject2,
                    alpha, path_func = straight_path):
        """
        Turns self into an interpolation between mobject1
        and mobject2.
        """
        self.points = path_func(
            mobject1.points, mobject2.points, alpha
        )
        self.interpolate_color(mobject1, mobject2, alpha)

    def interpolate_color(self, mobject1, mobject2, alpha):
        pass #To implement in subclass

    def become_partial(self, mobject, a, b):
        """
        Set points in such a way as to become only
        part of mobject.
        Inputs 0 <= a < b <= 1 determine what portion
        of mobject to become.
        """
        pass #To implement in subclasses

        #TODO, color?

    def pointwise_become_partial(self, mobject, a, b):
        pass #To implement in subclass

class Group(Mobject):
    #Alternate name to improve readibility in cases where
    #the mobject is used primarily for its submobject housing
    #functionality.
    pass
