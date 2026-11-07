"""Pose from the cyan/magenta reference displayed by firmware MARKER mode."""
import argparse
import json
import math
import numpy as np
from PIL import Image


def largest_component(mask):
    remaining = set(zip(*np.nonzero(mask)))
    largest = []
    while remaining:
        seed = remaining.pop()
        component, pending = [seed], [seed]
        while pending:
            y, x = pending.pop()
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    neighbor = (y+dy,x+dx)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.append(neighbor)
                        pending.append(neighbor)
        if len(component)>len(largest):
            largest = component
    if len(largest)<4:
        raise ValueError('Reference marker missing or too small')
    return np.array(largest)


def marker_pose(image, box, front='magenta'):
    if front not in ('magenta','cyan'):
        raise ValueError('Front must be magenta or cyan')
    x,y,w,h = box
    if min(x,y)<0 or min(w,h)<8 or x+w>image.width or y+h>image.height:
        raise ValueError('Invalid marker crop')
    rgb = np.asarray(image.convert('RGB'), dtype=float)[y:y+h,x:x+w]
    r,g,b = rgb.transpose(2,0,1)
    cyan = (np.minimum(g,b)>45) & (g>1.35*r) & (b>1.35*r) & (g>0.6*b)
    # The camera renders this panel's magenta block predominantly blue.
    # Use its measured blue/green contrast, not an assumed red response.
    magenta = (b>60) & (b>1.5*g)
    centers, counts = {}, {}
    for name, mask in [('cyan',cyan),('magenta',magenta)]:
        points = largest_component(mask)
        # Channel contrast provides subpixel centroids through anti-aliased edges.
        weights = ((np.minimum(g,b)-r) if name=='cyan' else (b-g))[points[:,0],points[:,1]]
        center_y, center_x = np.average(points, axis=0, weights=weights)
        centers[name] = np.array([center_x+x,center_y+y])
        counts[name] = len(points)
    tail = 'cyan' if front=='magenta' else 'magenta'
    vector = centers[front]-centers[tail]
    separation = float(np.linalg.norm(vector))
    if not 5 <= separation <= 80:
        raise ValueError('Implausible reference-marker separation')
    center = (centers['cyan']+centers['magenta'])/2
    return {'center_pixels':center.round(3).tolist(),
            'heading_degrees':round(math.degrees(math.atan2(vector[1],vector[0])),3),
            'marker_centers':{k:v.round(3).tolist() for k,v in centers.items()},
            'marker_pixels':counts, 'separation_pixels':round(separation,3),
            'algorithm':'screen-markers-v1',
            'units':'image pixels and clockwise degrees from image-right'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--box', nargs=4, type=int, required=True)
    parser.add_argument('--front', choices=['magenta','cyan'], default='magenta')
    args=parser.parse_args()
    print(json.dumps(marker_pose(Image.open(args.image),args.box,args.front),indent=2))
